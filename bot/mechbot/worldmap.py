"""Static map model: terrain heights, a walkability grid, line of sight, and a resumable A*.

Built once at `hello` (inside the 20 s hello budget) from the map files in `hello.map.dir`
(protocol.md section 11). Everything here is pure Python and allocation-light so that a
decision stays well inside the 50 ms tick budget.
"""
from __future__ import annotations

import heapq
import json
import math
import os
from array import array
from typing import List, Optional, Tuple

SQRT2 = math.sqrt(2.0)


class WorldMap:
    def __init__(self, map_dir: str, cell: float = 3.0, step_up: float = 1.2, head: float = 9.0,
                 max_slope_deg: float = 50.0):
        with open(os.path.join(map_dir, "v2", "world.json")) as f:
            world = json.load(f)
        tr = world["terrain"]
        self.t_minx, self.t_miny, self.t_step = tr["minX"], tr["minY"], tr["step"]
        self.t_nx, self.t_ny, self.t_scale = tr["nx"], tr["ny"], tr.get("scale", 0.01)
        self.terrain = array("h")
        with open(os.path.join(map_dir, "v2", tr.get("file", "terrain.i16")), "rb") as f:
            self.terrain.frombytes(f.read())
        if array("h", [1]).tobytes() != b"\x01\x00":  # file is little-endian
            self.terrain.byteswap()

        b = world["bounds"]
        self.minx, self.miny, self.maxx, self.maxy = b["minX"], b["minY"], b["maxX"], b["maxY"]
        self.cell = cell
        self.nx = int(math.ceil((self.maxx - self.minx) / cell))
        self.ny = int(math.ceil((self.maxy - self.miny) / cell))
        n = self.nx * self.ny
        self.blocked = bytearray(n)
        self.roof = array("f", [-1e9]) * n          # highest solid top in the cell (for line of sight)
        self.gnd = array("f", [0.0]) * n            # ground height at the cell centre
        self.pid = array("i", [-1]) * n             # index of the prism that sets `roof` in the cell
        self.prisms = world["prisms"]
        for j in range(self.ny):
            y = self.miny + (j + 0.5) * cell
            for i in range(self.nx):
                self.gnd[j * self.nx + i] = self.ground(self.minx + (i + 0.5) * cell, y)
        for pi, p in enumerate(world["prisms"]):
            self._raster(p, step_up, head, pi)
        # terrain too steep to walk: mark cells whose height jumps more than the slope allows
        lim = cell * math.tan(math.radians(max_slope_deg))
        g, nx = self.gnd, self.nx
        for j in range(self.ny - 1):
            for i in range(nx - 1):
                k = j * nx + i
                if abs(g[k + 1] - g[k]) > lim or abs(g[k + nx] - g[k]) > lim:
                    self.blocked[k] = 1
        # cover: free cells with a tall solid within 2 cells (a wall at our back blocks shots and sight)
        self.cover = bytearray(n)
        for k in range(n):
            if self.blocked[k] and self.roof[k] > self.gnd[k] + 6.0:
                j, i = divmod(k, self.nx)
                for jj in range(max(j - 2, 0), min(j + 3, self.ny)):
                    for ii in range(max(i - 2, 0), min(i + 3, self.nx)):
                        kk = jj * self.nx + ii
                        if self.cover[kk] < 255:
                            self.cover[kk] += 1
        # map edge is a wall
        for i in range(self.nx):
            self.blocked[i] = self.blocked[(self.ny - 1) * self.nx + i] = 1
        for j in range(self.ny):
            self.blocked[j * self.nx] = self.blocked[j * self.nx + self.nx - 1] = 1

    # ------------------------------------------------------------------ geometry
    def ground(self, x: float, y: float) -> float:
        fx = (x - self.t_minx) / self.t_step
        fy = (y - self.t_miny) / self.t_step
        i = min(max(int(fx), 0), self.t_nx - 2)
        j = min(max(int(fy), 0), self.t_ny - 2)
        ax, ay = min(max(fx - i, 0.0), 1.0), min(max(fy - j, 0.0), 1.0)
        t, nx = self.terrain, self.t_nx
        k = j * nx + i
        h0 = t[k] * (1 - ax) + t[k + 1] * ax
        h1 = t[k + nx] * (1 - ax) + t[k + nx + 1] * ax
        return (h0 * (1 - ay) + h1 * ay) * self.t_scale

    def _raster(self, p: dict, step_up: float, head: float, pi: int = -1) -> None:
        rings = [p["ring"]] + list(p.get("holes") or [])
        edges = []
        ymin, ymax = 1e18, -1e18
        for r in rings:
            pts = [(r[i], r[i + 1]) for i in range(0, len(r) - 1, 2)]
            for a, c in zip(pts, pts[1:] + pts[:1]):
                if a[1] != c[1]:
                    edges.append((a[0], a[1], c[0], c[1]))
                ymin, ymax = min(ymin, a[1]), max(ymax, a[1])
        if not edges:
            return
        base, top = p["base"], p["top"]
        cell, nx = self.cell, self.nx
        y = math.floor(ymin) + 0.5
        while y < ymax:
            xs = []
            for x0, y0, x1, y1 in edges:
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            j = int((y - self.miny) // cell)
            if 0 <= j < self.ny:
                for a, c in zip(xs[0::2], xs[1::2]):
                    g = self.ground((a + c) / 2, y)
                    solid = top > g + step_up and base < g + head
                    i0 = max(int((a - self.minx) // cell), 0)
                    i1 = min(int((c - self.minx) // cell), nx - 1)
                    for i in range(i0, i1 + 1):
                        k = j * nx + i
                        if top > self.roof[k]:
                            self.roof[k] = top
                            self.pid[k] = pi
                        if solid:
                            self.blocked[k] = 1
            y += 1.0

    def idx(self, x: float, y: float) -> int:
        i = min(max(int((x - self.minx) // self.cell), 0), self.nx - 1)
        j = min(max(int((y - self.miny) // self.cell), 0), self.ny - 1)
        return j * self.nx + i

    def center(self, k: int) -> Tuple[float, float]:
        j, i = divmod(k, self.nx)
        return self.minx + (i + 0.5) * self.cell, self.miny + (j + 0.5) * self.cell

    def free(self, x: float, y: float) -> bool:
        return not self.blocked[self.idx(x, y)]

    def nearest_free(self, x: float, y: float, max_r: int = 12) -> int:
        k = self.idx(x, y)
        if not self.blocked[k]:
            return k
        j0, i0 = divmod(k, self.nx)
        for r in range(1, max_r + 1):
            best, bd = -1, 1e18
            for j in range(j0 - r, j0 + r + 1):
                for i in (range(i0 - r, i0 + r + 1) if j in (j0 - r, j0 + r) else (i0 - r, i0 + r)):
                    if 0 <= i < self.nx and 0 <= j < self.ny and not self.blocked[j * self.nx + i]:
                        d = (i - i0) ** 2 + (j - j0) ** 2
                        if d < bd:
                            best, bd = j * self.nx + i, d
            if best >= 0:
                return best
        return k

    def los(self, a: List[float], b: List[float], step: float = 2.0) -> bool:
        """True if the segment a->b (3D) clears every building roof and the terrain."""
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        d = math.hypot(dx, dy)
        n = max(int(d / step), 1)
        roof = self.roof
        for s in range(1, n):
            f = s / n
            x, y, z = a[0] + dx * f, a[1] + dy * f, a[2] + dz * f
            k = self.idx(x, y)
            if roof[k] > z or self.gnd[k] > z + 0.5:
                return False
        return True

    def elevated(self, x: float, y: float, z: float) -> bool:
        """Standing on a structure (a roof) rather than on the terrain."""
        k = self.idx(x, y)
        return z > self.gnd[k] + 2.5 and abs(self.roof[k] - z) < 1.5

    def walk_ok(self, x: float, y: float, z: Optional[float] = None) -> bool:
        """Can we stand at (x, y)? On the ground: not a wall. On a roof at height z: still the same roof level."""
        k = self.idx(x, y)
        if z is not None and z > self.gnd[k] + 2.5:
            return abs(self.roof[k] - z) < 1.0
        return not self.blocked[k]

    def line_walkable(self, a: Tuple[float, float], b: Tuple[float, float]) -> bool:
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(int(d / (self.cell * 0.5)), 1)
        for s in range(1, n + 1):
            f = s / n
            if self.blocked[self.idx(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)]:
                return False
        return True


class PathSearch:
    """A* on the walkability grid that can be paused and resumed across ticks (node budget per call)."""

    def __init__(self, wm: WorldMap, start: int, goal: int):
        self.wm, self.start, self.goal = wm, start, goal
        self.gx, self.gy = divmod(goal, wm.nx)[1], divmod(goal, wm.nx)[0]
        self.g = {start: 0.0}
        self.came = {start: -1}
        self.open = [(self._h(start), start)]
        self.done = False
        self.path: Optional[List[Tuple[float, float]]] = None
        self.best = (self._h(start), start)  # closest node so far (partial path fallback)

    def _h(self, k: int) -> float:
        j, i = divmod(k, self.wm.nx)
        dx, dy = abs(i - self.gx), abs(j - self.gy)
        return (dx + dy) + (SQRT2 - 2) * min(dx, dy)

    def step(self, budget: int) -> bool:
        if self.done:
            return True
        wm, nx, blk = self.wm, self.wm.nx, self.wm.blocked
        g, came, op = self.g, self.came, self.open
        nbrs = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2))
        while op and budget > 0:
            budget -= 1
            f, k = heapq.heappop(op)
            if k == self.goal:
                self._finish(k)
                return True
            gk = g[k]
            if f - self._h(k) > gk + 1e-9:
                continue  # stale entry
            h = f - gk
            if h < self.best[0]:
                self.best = (h, k)
            j, i = divmod(k, nx)
            for di, dj, c in nbrs:
                ii, jj = i + di, j + dj
                if not (0 <= ii < nx and 0 <= jj < wm.ny):
                    continue
                n = jj * nx + ii
                if blk[n]:
                    continue
                if di and dj and (blk[j * nx + ii] or blk[jj * nx + i]):
                    continue  # no corner cutting
                ng = gk + c
                if ng < g.get(n, 1e18):
                    g[n] = ng
                    came[n] = k
                    heapq.heappush(op, (ng + self._h(n), n))
        if not op:
            self._finish(self.best[1])  # unreachable: go as close as we can
            return True
        return False

    def _finish(self, k: int) -> None:
        cells = []
        while k != -1:
            cells.append(k)
            k = self.came[k]
        cells.reverse()
        self.path = [self.wm.center(c) for c in cells]
        self.done = True
