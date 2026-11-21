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
