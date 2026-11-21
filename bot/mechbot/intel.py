"""Intel: where enemy mechs probably are, from everything the protocol tells us, not only what we see.

Sources (protocol sections 6 and 8), most precise first:
  seen       obs.mechs (kind "mech"): exact position, also for memory_s after it leaves view
  beam       obs.beams: a laser/lightning `path` starts at the shooter's muzzle -> exact shooter position
  damaged    events: bearing to the attacker; distance from its weapon (lightning reaches 45 m) or from a
             matching gunfire sound, else a default
  bullet     obs.projectiles of kind "gun" flying toward us: the shooter lies back along the bullet's path
  sound      obs.sounds: bearing (7 degree noise) and near / mid / far; footsteps (40 m), boost and jets (90 m),
             reloads (60 m), gunfire, laser charge, lightning ... each says someone is there; weapon sounds
             also say what it holds
Every estimate has a confidence that decays with age; anonymous estimates (sounds, unseen damage) merge by
bearing and are dropped once a seen mech accounts for them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# sound kind -> (confidence it is a mech worth tracking, weapon it implies)
SOUND_KINDS = {
    "step": (0.55, None), "boost": (0.55, None), "jet": (0.6, None), "reload": (0.6, "gun"),
    "gun": (0.6, "gun"), "laser_charge": (0.75, "laser"), "laser": (0.6, "laser"),
    "lightning": (0.6, "lightning"), "mortar": (0.5, "mortar"),
}
DIST_GUESS = {"near": 35.0, "mid": 110.0, "far": 230.0}


@dataclass
class Threat:
    key: str
    pos: List[float]
    t: float
    conf: float
    src: str
    mech_id: Optional[int] = None
    weapons: List[str] = field(default_factory=list)
    hostile_t: float = -1e9          # last time this one damaged us

    def conf_at(self, t: float, half_life: float) -> float:
        return self.conf * 0.5 ** (max(t - self.t, 0.0) / half_life)


class Intel:
    def __init__(self, cfg: Any, rules: Dict[str, Any]):
        self.cfg = cfg
        self.rules = rules
        self.threats: Dict[str, Threat] = {}
        self.anon = 0
        self.sound_range = rules.get("sound", {}).get("range", {})

    # ------------------------------------------------------------------ ingest
    def update(self, obs: Dict[str, Any]) -> None:
        t, me = obs["t"], obs["self"]
        pos = me["pos"]
        seen = [m for m in obs.get("mechs", []) if m["kind"] == "mech"]
        for m in seen:
            th = self._by_id(m["id"], t)
            th.pos, th.t, th.conf, th.src = list(m["pos"]), t, 1.0, "seen"
            th.weapons = list(m.get("weapons", th.weapons))
        for b in obs.get("beams", []):
            if b.get("by") is None or b["by"] >= 100 or not b.get("path"):
                continue
            th = self._by_id(b["by"], t)
            if th.src != "seen" or t - th.t > 0.2:
                p = b["path"][0]
                th.pos = [p[0], p[1], p[2] - 7.0]
                th.t, th.conf, th.src = t - b.get("age", 0.0), 0.95, "beam"
            if b["kind"] not in th.weapons:
                th.weapons.append(b["kind"])
        gun_bearings = [(s["bearing"], s["dist"]) for s in obs.get("sounds", []) if s["kind"] == "gun"]
        for e in obs.get("events", []):
            if e.get("type") != "damaged" or e.get("by") is None or e["by"] >= 100 or e.get("bearing") is None:
                continue
            th = self._by_id(e["by"], t)
            th.hostile_t = t
            if th.src in ("seen", "beam") and t - th.t < 1.0:
                continue
            dist = self._damage_dist(e, gun_bearings)
            b = e["bearing"]
            th.pos = [pos[0] + math.cos(b) * dist, pos[1] + math.sin(b) * dist, pos[2]]
            th.t, th.conf, th.src = t, 0.6, "damaged"
            if e.get("weapon") in ("gun", "laser", "lightning", "mortar") and e["weapon"] not in th.weapons:
                th.weapons.append(e["weapon"])
        for p in obs.get("projectiles", []):
            if p.get("kind") != "gun":
                continue
            v = p["vel"]
            sp = math.hypot(v[0], v[1]) or 1.0
            to_me = (pos[0] - p["pos"][0], pos[1] - p["pos"][1])
            if (v[0] * to_me[0] + v[1] * to_me[1]) / sp < 0.8 * math.hypot(*to_me):
                continue                                   # not coming at us
            back = math.atan2(-v[1], -v[0])                # the shooter is back along the path
            self._anon_merge([p["pos"][0] + math.cos(back) * 60.0, p["pos"][1] + math.sin(back) * 60.0, pos[2]],
                             t, 0.5, "bullet", pos)
        for s in obs.get("sounds", []):
            k = s["kind"]
            if k not in SOUND_KINDS:
                continue
            conf, weapon = SOUND_KINDS[k]
            rng = self.sound_range.get(k, 160.0)
            dist = min(DIST_GUESS.get(s["dist"], 110.0), rng * 0.75)
            b = s["bearing"]
            est = [pos[0] + math.cos(b) * dist, pos[1] + math.sin(b) * dist, pos[2]]
            # a seen mech near that bearing explains the sound: nothing new
            if any(self._bearing_close(pos, m["pos"], b, 0.3) for m in seen):
                continue
            th = self._anon_merge(est, t - s.get("age", 0.0), conf, "sound:" + k, pos)
            if weapon and weapon not in th.weapons:
                th.weapons.append(weapon)
        # anonymous estimates a seen mech now accounts for
        for key in [k for k, th in self.threats.items() if th.mech_id is None]:
            th = self.threats[key]
            if any(math.dist(th.pos[:2], m["pos"][:2]) < self.cfg.intel_merge_m for m in seen):
                del self.threats[key]
        for key in [k for k, th in self.threats.items() if th.conf_at(t, self.cfg.intel_half_life_s) < 0.08]:
            del self.threats[key]

    def _by_id(self, mid: int, t: float) -> Threat:
        key = f"m{int(mid)}"
        if key not in self.threats:
            self.threats[key] = Threat(key, [0.0, 0.0, 0.0], t, 0.0, "new", int(mid))
        return self.threats[key]

    def _damage_dist(self, e: Dict[str, Any], gun_bearings) -> float:
        w = e.get("weapon")
        if w == "lightning":
            return 30.0
        for b, dist in gun_bearings:
            if abs((b - e["bearing"] + math.pi) % (2 * math.pi) - math.pi) < 0.35:
                return DIST_GUESS[dist]
        return self.cfg.unseen_dist

    @staticmethod
    def _bearing_close(me, p, bearing, tol) -> bool:
        b = math.atan2(p[1] - me[1], p[0] - me[0])
        return abs((b - bearing + math.pi) % (2 * math.pi) - math.pi) < tol

    def _anon_merge(self, est, t, conf, src, me) -> Threat:
        b = math.atan2(est[1] - me[1], est[0] - me[0])
        for th in self.threats.values():
            if th.mech_id is None and self._bearing_close(me, th.pos, b, 0.4):
                w = 0.5
                th.pos = [th.pos[i] * (1 - w) + est[i] * w for i in range(3)]
                th.t = max(th.t, t)
                th.conf = min(max(th.conf, conf) + 0.1, 0.9)
                th.src = src
                return th
        self.anon += 1
        th = Threat(f"a{self.anon}", list(est), t, conf, src)
        self.threats[th.key] = th
        return th

    # ------------------------------------------------------------------ queries
    def active(self, t: float, me: List[float], min_conf: float = 0.25, max_dist: float = 260.0) -> List[Threat]:
        out = []
        for th in self.threats.values():
            c = th.conf_at(t, self.cfg.intel_half_life_s)
            if c >= min_conf and math.dist(th.pos[:2], me[:2]) < max_dist:
                out.append(th)
        out.sort(key=lambda th: -self.danger(th, t, me))
        return out

    def danger(self, th: Threat, t: float, me: List[float]) -> float:
        c = th.conf_at(t, self.cfg.intel_half_life_s)
        d = math.dist(th.pos[:2], me[:2])
        hostile = 2.0 if t - th.hostile_t < 6.0 else 1.0
        return c * hostile / (1.0 + d / 60.0)
