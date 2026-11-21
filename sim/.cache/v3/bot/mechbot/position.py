"""Where to stand: perches (reachable roofs) and covered ground spots, scored for survival.

Built once at `hello` from the map. Each time the next zone circle is announced (and every few seconds
after, with hysteresis), `PositionPlanner.choose` scores every candidate inside that circle:

    score = w_height * height advantage        roofs see further, shoot down, and are out of drone reach
          + w_cover  * walls around the spot   a wall at our back blocks shots and sight
          + w_room   * flat room on the roof   space to strafe without falling off
          - w_center * distance to the circle centre / radius   later circles fall inside this one
          - w_travel * travel time / time left before the shrink ends
          - w_crowd  * visible mechs near the spot,  - w_npc * drones near the spot
          + hysteresis for the spot we already hold

and returns the best Spot. Roof heights the jetpack cannot reach with our current energy are skipped.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .worldmap import WorldMap


@dataclass
class Perch:
    pid: int
    top: float
    height: float                 # roof top above the ground at its launch cells
    cells: List[int]              # interior roof cells (at least one cell from every edge)
    launch: List[int]             # free ground cells next to the building, to jet up from


@dataclass
class Spot:
    kind: str                     # "roof" | "ground"
    x: float
    y: float
    z: float
    perch: Optional[Perch] = None
    score: float = 0.0
    why: str = ""
    parts: Dict[str, float] = field(default_factory=dict)


def build_perches(wm: WorldMap, min_height: float, min_cells: int) -> List[Perch]:
    nx, ny = wm.nx, wm.ny
    roof, pid, gnd, blk = wm.roof, wm.pid, wm.gnd, wm.blocked
    by_pid: Dict[int, List[int]] = {}
    for k in range(nx * ny):
        p = pid[k]
        if p >= 0:
            by_pid.setdefault(p, []).append(k)
    out: List[Perch] = []
    for p, ks in by_pid.items():
        prism = wm.prisms[p]
        if prism.get("kind") != "building":
            continue
        top = prism["top"]
        interior = []
        for k in ks:
            j, i = divmod(k, nx)
            if 0 < i < nx - 1 and 0 < j < ny - 1 and all(
                    abs(roof[(j + dj) * nx + i + di] - top) < 0.3
                    for dj in (-1, 0, 1) for di in (-1, 0, 1)):
                interior.append(k)
        if len(interior) < min_cells:
            continue
        launch = set()
        for k in ks:
            j, i = divmod(k, nx)
            for dj in (-2, -1, 0, 1, 2):
                for di in (-2, -1, 0, 1, 2):
                    jj, ii = j + dj, i + di
                    if 0 <= jj < ny and 0 <= ii < nx:
                        kk = jj * nx + ii
                        if not blk[kk] and roof[kk] < gnd[kk] + 1.0:
                            launch.add(kk)
        if not launch:
            continue
        launch_l = sorted(launch)
        base = sorted(gnd[k] for k in launch_l)[len(launch_l) // 2]
        height = top - base
        if height < min_height:
            continue
        out.append(Perch(p, top, height, interior, launch_l))
    return out


class PositionPlanner:
    def __init__(self, wm: WorldMap, cfg: Any, rules: Dict[str, Any]):
        self.wm, self.cfg, self.rules = wm, cfg, rules
        self.perches = build_perches(wm, cfg.perch_min_height, cfg.perch_min_cells)

    def climb_max(self, me: Dict[str, Any]) -> float:
        """Highest roof we can reach on a full tank: jet climbs max_rise_speed for jet_drain energy a second."""
        st = me.get("stats", {})
        mech = self.rules.get("mech", {})
        rise = st.get("max_rise_speed", mech.get("max_rise_speed", 10.0))
        drain = st.get("jet_drain", mech.get("jet_drain", 15.0))
        g = st.get("gravity", mech.get("gravity", 22.0))
        jump = st.get("jump_speed", mech.get("jump_speed", 11.0))
        return self.cfg.climb_safety * me.get("max_energy", 100.0) * rise / max(drain, 1e-6) + jump * jump / (2 * g)

    def choose(self, obs: Dict[str, Any], current: Optional[Spot], bad: Dict[int, float]) -> Spot:
        cfg, wm, me, t, z = self.cfg, self.wm, obs["self"], obs["t"], obs["zone"]
        pos = me["pos"]
        nc, nr = z["next_center"], z["next_radius"]
        if nr <= 1.0:
            return Spot("ground", nc[0], nc[1], wm.ground(nc[0], nc[1]), why="final circle centre")
        margin = min(cfg.zone_margin, nr * 0.3)
        lim = nr - margin
        speed = me["stats"].get("walk_speed", 11.7)
        avail = max(z["shrink_end"] - t, 8.0)
        mechs = [m for m in obs["mechs"] if m["kind"] == "mech"]
        npcs = [m for m in obs["mechs"] if m["kind"] == "npc"]
        cmax = self.climb_max(me)
        best: Optional[Spot] = None

        def common(x: float, y: float, travel: float) -> Tuple[float, Dict[str, float]]:
            parts = {
                "center": -cfg.w_center * math.hypot(x - nc[0], y - nc[1]) / max(nr, 1.0),
                "travel": -cfg.w_travel * travel / avail,
                "crowd": -cfg.w_crowd * sum(1 for m in mechs if math.hypot(m["pos"][0] - x, m["pos"][1] - y) < 80),
                "npc": -cfg.w_npc * sum(1 for n in npcs if math.hypot(n["pos"][0] - x, n["pos"][1] - y) < 55),
            }
            if current is not None and math.hypot(current.x - x, current.y - y) < 4.0:
                parts["stay"] = cfg.w_stay
            return sum(parts.values()), parts

        # roofs
        if cfg.use_perches:
            for p in self.perches:
                if bad.get(p.pid, -1) > t or p.height > cmax:
                    continue
                k = min(p.cells, key=lambda c: (wm.center(c)[0] - nc[0]) ** 2 + (wm.center(c)[1] - nc[1]) ** 2)
                x, y = wm.center(k)
                if math.hypot(x - nc[0], y - nc[1]) > lim:
                    continue
                lk = min(p.launch, key=lambda c: (wm.center(c)[0] - pos[0]) ** 2 + (wm.center(c)[1] - pos[1]) ** 2)
                lx, ly = wm.center(lk)
                on_it = wm.elevated(pos[0], pos[1], pos[2]) and abs(pos[2] - p.top) < 1.5
                travel = 0.0 if on_it else math.hypot(lx - pos[0], ly - pos[1]) * 1.3 / speed + p.height / 8.0 + 3.0
                if travel > avail:
                    continue
                s, parts = common(x, y, travel)
                parts["height"] = cfg.w_height * min(p.height, cfg.height_cap) / cfg.height_cap
                parts["room"] = cfg.w_room * min(len(p.cells), 40) / 40.0
                s += parts["height"] + parts["room"]
                if best is None or s > best.score:
                    best = Spot("roof", x, y, p.top, p, s, f"roof {p.height:.0f}m", parts)
        # covered ground, sampled on a coarse lattice inside the circle (plus where we stand)
        r_cells = int(lim / wm.cell)
        stride = max(cfg.ground_stride, int(math.ceil(r_cells * math.sqrt(math.pi / cfg.ground_samples))))
        ci, cj = int((nc[0] - wm.minx) // wm.cell), int((nc[1] - wm.miny) // wm.cell)
        cand = [wm.idx(pos[0], pos[1])]
        for jj in range(max(cj - r_cells, 0), min(cj + r_cells + 1, wm.ny), stride):
            for ii in range(max(ci - r_cells, 0), min(ci + r_cells + 1, wm.nx), stride):
                cand.append(jj * wm.nx + ii)
        for k in cand:
            if wm.blocked[k]:
                continue
            x, y = wm.center(k)
            if math.hypot(x - nc[0], y - nc[1]) > lim:
                continue
            travel = math.hypot(x - pos[0], y - pos[1]) * 1.3 / speed
            if travel > avail:
                continue
            s, parts = common(x, y, travel)
            parts["cover"] = cfg.w_cover * min(wm.cover[k], 8) / 8.0
            s += parts["cover"]
            if best is None or s > best.score:
                best = Spot("ground", x, y, wm.gnd[k], None, s, f"ground cover {wm.cover[k]}", parts)
        if best is None:  # nothing reachable in time: head for the centre
            return Spot("ground", nc[0], nc[1], wm.ground(nc[0], nc[1]), why="no spot in time: centre")
        return best

    def launch_for(self, p: Perch, pos: List[float]) -> Tuple[float, float]:
        k = min(p.launch, key=lambda c: (self.wm.center(c)[0] - pos[0]) ** 2 + (self.wm.center(c)[1] - pos[1]) ** 2)
        return self.wm.center(k)

    def nearest_roof_cell(self, p: Perch, pos: List[float]) -> Tuple[float, float]:
        """Closest cell of the building (edge included) to jet toward from the launch point."""
        wm = self.wm
        best, bd = None, 1e18
        for k in self._cells_of(p):
            x, y = wm.center(k)
            d = (x - pos[0]) ** 2 + (y - pos[1]) ** 2
            if d < bd:
                best, bd = (x, y), d
        return best or wm.center(p.cells[0])

    def _cells_of(self, p: Perch) -> List[int]:
        if not hasattr(p, "_all"):
            wm = self.wm
            j0 = [divmod(k, wm.nx) for k in p.cells]
            js, is_ = [a for a, _ in j0], [b for _, b in j0]
            allc = []
            for j in range(max(min(js) - 3, 0), min(max(js) + 4, wm.ny)):
                for i in range(max(min(is_) - 3, 0), min(max(is_) + 4, wm.nx)):
                    k = j * wm.nx + i
                    if wm.pid[k] == p.pid:
                        allc.append(k)
            p._all = allc  # type: ignore[attr-defined]
        return p._all  # type: ignore[attr-defined]
