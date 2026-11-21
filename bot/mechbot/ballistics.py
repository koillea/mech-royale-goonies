"""Aiming maths: angle helpers, lead for straight projectiles, and mortar elevation."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def yaw_to(src: List[float], dst: List[float]) -> float:
    return math.atan2(dst[1] - src[1], dst[0] - src[0])


def aim_at(src: List[float], dst: List[float]) -> Tuple[float, float]:
    """[yaw, pitch] from point src to point dst (both 3D)."""
    dx, dy, dz = dst[0] - src[0], dst[1] - src[1], dst[2] - src[2]
    return math.atan2(dy, dx), math.atan2(dz, math.hypot(dx, dy))


def lead(src: List[float], tpos: List[float], tvel: List[float], speed: float,
         gravity_z: bool = False) -> List[float]:
    """Point to aim at so a projectile of `speed` from src meets a target moving at constant tvel.
    Falls back to the target's current position when no intercept exists."""
    rx, ry, rz = tpos[0] - src[0], tpos[1] - src[1], tpos[2] - src[2]
    vx, vy, vz = tvel[0], tvel[1], 0.0 if gravity_z else tvel[2]
    a = vx * vx + vy * vy + vz * vz - speed * speed
    b = 2 * (rx * vx + ry * vy + rz * vz)
    c = rx * rx + ry * ry + rz * rz
    t: Optional[float] = None
    if abs(a) < 1e-9:
        if abs(b) > 1e-9:
            t = -c / b
    else:
        disc = b * b - 4 * a * c
        if disc >= 0:
            s = math.sqrt(disc)
            cands = [x for x in ((-b - s) / (2 * a), (-b + s) / (2 * a)) if x > 0]
            t = min(cands) if cands else None
    if t is None or t <= 0 or t > 3.0:
        return list(tpos)
    return [tpos[0] + vx * t, tpos[1] + vy * t, tpos[2] + vz * t]


def mortar_pitch(dist: float, dz: float, speed: float, g: float) -> Optional[float]:
    """Low-arc launch pitch to hit a point `dist` away horizontally and `dz` higher. None if out of range."""
    v2 = speed * speed
    disc = v2 * v2 - g * (g * dist * dist + 2 * dz * v2)
    if disc < 0 or dist < 1e-6:
        return None
    return math.atan((v2 - math.sqrt(disc)) / (g * dist))


def mortar_time(dist: float, pitch: float, speed: float) -> float:
    return dist / max(speed * math.cos(pitch), 1e-6)


class Tracker:
    """O1: per-target motion history from successive observations: acceleration and strafe rhythm.

    Acceleration is the change of the observed velocity between decisions (smoothed). The strafe rhythm is the
    time between sign flips of the target's sideways velocity (relative to us): once the current leg is older
    than this target's typical leg, a reversal is due and the sideways lead is shrunk toward zero.
    """

    def __init__(self):
        self.last = {}       # id -> (t, vel)
        self.acc = {}        # id -> [ax, ay]
        self.side = {}       # id -> (sign, since_t)
        self.legs = {}       # id -> recent leg lengths

    def update(self, t: float, me_pos: List[float], mechs) -> None:
        for m in mechs:
            if m.get("kind") != "mech":
                continue
            i, v = m["id"], m.get("vel", [0.0, 0.0, 0.0])
            if i in self.last:
                t0, v0 = self.last[i]
                dt = t - t0
                if 0.01 < dt < 0.35:
                    ax, ay = (v[0] - v0[0]) / dt, (v[1] - v0[1]) / dt
                    pa = self.acc.get(i, [ax, ay])
                    self.acc[i] = [0.5 * pa[0] + 0.5 * ax, 0.5 * pa[1] + 0.5 * ay]
                else:
                    self.acc[i] = [0.0, 0.0]
            self.last[i] = (t, list(v))
            dx, dy = m["pos"][0] - me_pos[0], m["pos"][1] - me_pos[1]
            d = math.hypot(dx, dy) or 1.0
            lat = (v[0] * -dy + v[1] * dx) / d
            if abs(lat) > 3.0:
                sg = 1 if lat > 0 else -1
                s0 = self.side.get(i)
                if s0 is None:
                    self.side[i] = (sg, t)
                elif s0[0] != sg:
                    leg = t - s0[1]
                    if 0.2 < leg < 6.0:
                        self.legs.setdefault(i, []).append(leg)
                        self.legs[i] = self.legs[i][-8:]
                    self.side[i] = (sg, t)

    def reversal_due(self, i: int, t: float) -> float:
        """0 = no reversal expected yet, up to 1 = the current leg is well past this target's usual length."""
        legs, s = self.legs.get(i), self.side.get(i)
        if not legs or len(legs) < 2 or s is None:
            return 0.0
        typical = sorted(legs)[len(legs) // 2]
        age = t - s[1]
        return max(0.0, min(1.0, (age - 0.8 * typical) / max(0.4 * typical, 0.1)))


def predict(tpos: List[float], tvel: List[float], tacc: List[float], t: float, vmax: float,
            g: float = 0.0, ground: Optional[float] = None) -> List[float]:
    """Target position after t seconds: horizontal velocity changes at the observed acceleration for at most
    0.4 s (then holds), capped at vmax; vertical falls under gravity g when airborne, down to `ground`."""
    ta = min(t, 0.4)
    vx1, vy1 = tvel[0] + tacc[0] * ta, tvel[1] + tacc[1] * ta
    s1 = math.hypot(vx1, vy1)
    if s1 > vmax:
        vx1, vy1 = vx1 * vmax / s1, vy1 * vmax / s1
    # distance: average velocity over the accelerating part, then the final velocity
    x = tpos[0] + (tvel[0] + vx1) / 2 * ta + vx1 * (t - ta)
    y = tpos[1] + (tvel[1] + vy1) / 2 * ta + vy1 * (t - ta)
    z = tpos[2] + tvel[2] * t - 0.5 * g * t * t if g > 0 else tpos[2] + tvel[2] * t
    if ground is not None:
        z = max(z, ground)
    return [x, y, z]


def intercept(src: List[float], tpos: List[float], tvel: List[float], tacc: List[float], speed: Optional[float],
              delay: float, vmax: float, g: float = 0.0, ground: Optional[float] = None) -> List[float]:
    """Aim point: where the target will be when the shot reaches it. speed None = hitscan (laser).
    delay = time before the shot leaves (our decision interval)."""
    t = delay
    p = predict(tpos, tvel, tacc, t, vmax, g, ground)
    if speed is None:
        return p
    for _ in range(4):
        fl = math.dist(src, p) / speed
        if fl > 3.0:
            return list(tpos)
        p = predict(tpos, tvel, tacc, delay + fl, vmax, g, ground)
    return p
