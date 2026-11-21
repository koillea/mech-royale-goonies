"""Target tracking and prediction for aiming.

Every visible (or remembered, protocol section 8) mech and drone gets a short history of positions and
velocities. `predict(id, dt)` says where it will be `dt` seconds from now:

- steady movers: current velocity;
- strafers (the sideways velocity has reversed at least `reversals_for_mean` times in the window): the drift
  velocity over the window, i.e. aim at the centre of the jitter instead of chasing each leg;
- airborne targets (vertical speed above 1 m/s and feet above the ground): ballistic height with gravity,
  never below the ground;
- the predicted point is pulled back along the path if it would be inside a wall (mechs slide, they do not
  pass through).

`intercept` solves for the flight time of a straight shot against that (non-linear) prediction by fixed-point
iteration, starting from the decision latency (an action applies for the next 2 ticks, section 2).
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

Sample = Tuple[float, List[float], List[float]]   # (t, pos, vel)


class TargetTracker:
    def __init__(self, wm: Any = None, gravity: float = 22.0, window_s: float = 2.0, reversals_for_mean: int = 2):
        self.wm = wm
        self.g = gravity
        self.window = window_s
        self.rev_mean = reversals_for_mean
        self.hist: Dict[int, Deque[Sample]] = {}

    def update(self, obs: Dict[str, Any]) -> None:
        t = obs["t"]
        for m in obs.get("mechs", []):
            h = self.hist.setdefault(int(m["id"]), deque())
            if not h or t > h[-1][0] + 1e-6:
                h.append((t, list(m["pos"]), list(m.get("vel", [0.0, 0.0, 0.0]))))
            while h and t - h[0][0] > self.window:
                h.popleft()
        for k in [k for k, h in self.hist.items() if not h or t - h[-1][0] > 8.0]:
            del self.hist[k]

    def last(self, tid: int) -> Optional[Sample]:
        h = self.hist.get(int(tid))
        return h[-1] if h else None

    def reversals(self, tid: int, observer: List[float]) -> int:
        """Sign changes of the velocity component across our line of sight (strafe leg reversals)."""
        h = self.hist.get(int(tid))
        if not h or len(h) < 3:
            return 0
        p = h[-1][1]
        dx, dy = p[0] - observer[0], p[1] - observer[1]
        n = math.hypot(dx, dy) or 1.0
        px, py = -dy / n, dx / n                      # unit vector across the line of sight
        signs = []
        for _, _, v in h:
            s = v[0] * px + v[1] * py
            if abs(s) > 1.5:
                signs.append(s > 0)
        return sum(1 for a, b in zip(signs, signs[1:]) if a != b)

    def velocity(self, tid: int, observer: List[float]) -> List[float]:
        h = self.hist.get(int(tid))
        if not h:
            return [0.0, 0.0, 0.0]
        t1, p1, v1 = h[-1]
        if self.reversals(tid, observer) >= self.rev_mean and len(h) >= 4:
            t0, p0, _ = h[0]
            dt = max(t1 - t0, 1e-3)
            return [(p1[0] - p0[0]) / dt, (p1[1] - p0[1]) / dt, v1[2]]
        return list(v1)

    def predict(self, tid: int, dt: float, observer: List[float], pos: Optional[List[float]] = None,
                vel: Optional[List[float]] = None) -> List[float]:
        s = self.last(tid)
        if pos is None:
            if s is None:
                return list(observer)
            pos = s[1]
        v = self.velocity(tid, observer) if s is not None else (vel or [0.0, 0.0, 0.0])
        x, y = pos[0] + v[0] * dt, pos[1] + v[1] * dt
        z = pos[2]
        g0 = self.wm.ground(pos[0], pos[1]) if self.wm is not None else pos[2]
        if abs(v[2]) > 1.0 and pos[2] > g0 + 0.5:
            z = pos[2] + v[2] * dt - 0.5 * self.g * dt * dt
        if self.wm is not None:
            # do not predict through walls: back off along the path until the point is standable
            z_ref = pos[2] if self.wm.elevated(pos[0], pos[1], pos[2]) else None
            for f in (1.0, 0.75, 0.5, 0.25, 0.0):
                xx, yy = pos[0] + (x - pos[0]) * f, pos[1] + (y - pos[1]) * f
                if self.wm.walk_ok(xx, yy, z_ref):
                    x, y = xx, yy
                    break
            z = max(z, self.wm.ground(x, y) if z_ref is None else z_ref)
        return [x, y, z]

    def intercept(self, tid: int, muzzle: List[float], speed: float, z_off: float, latency: float = 0.05,
                  pos: Optional[List[float]] = None, vel: Optional[List[float]] = None) -> Tuple[List[float], float]:
        """Aim point (centre of mass, `z_off` above the feet) for a straight shot of `speed`, and its flight time."""
        tt = latency
        p = self.predict(tid, tt, muzzle, pos, vel)
        for _ in range(4):
            d = math.dist(muzzle, [p[0], p[1], p[2] + z_off])
            tt_new = latency + d / max(speed, 1e-6)
            p = self.predict(tid, tt_new, muzzle, pos, vel)
            if abs(tt_new - tt) < 1e-3:
                break
            tt = tt_new
        return [p[0], p[1], p[2] + z_off], tt


def rear_exposure(target: Dict[str, Any], observer: List[float], front_arc_deg: float = 180.0) -> float:
    """How far outside the target's front arc we stand: > 0 means our hits land on its back (x rear_mult)."""
    to_us = math.atan2(observer[1] - target["pos"][1], observer[0] - target["pos"][0])
    a = abs((to_us - target["aim"][0] + math.pi) % (2 * math.pi) - math.pi)
    return a - math.radians(front_arc_deg) / 2
