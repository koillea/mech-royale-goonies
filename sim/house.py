"""Stand-ins for the scorer's house bots, from the track rules (Sat Nov 21):

  "15 house bots (4 easy, 4 medium, 4 hard, 3 expert)", "acting as one squad: they share vision, never fight
  each other", and they "hunt you weakest first (one early, more as you thin them out, all of them late)".

Model (their real code is unknown):
- squad: house bots never target or damage each other (friendly fire is off in engine.py);
- omniscient (default, observed on the board): the squad always knows every entrant's position
  (SIM_OMNISCIENT=0: known only while any house bot has seen it in the last memory_s);
- hunters: the first k of a fixed random order of house bots, k = 1 + (house bots dead), all of them once
  t >= SIM_ALL_HUNT_T (default 300 s, "late"); hunters chase the weakest known entrant, or its last known
  position, and fight it at a preferred range;
- the rest hold a random point inside the next circle and fight an entrant only when it is within
  SIM_DEFEND_RANGE or has hit them in the last 5 s;
- skill levels differ by aim error, reaction delay and strafing; all move into the next circle in time.
"""
from __future__ import annotations

import math
import os
import random
from typing import Any, Dict, List, Optional

LEVELS = {
    #          aim error deg, reaction s, strafe, preferred range m
    "easy":   (3.5, 0.9, False, 60.0),
    "medium": (2.2, 0.6, False, 70.0),
    "hard":   (1.3, 0.4, True, 80.0),
    "expert": (0.7, 0.25, True, 90.0),
}
FIELD = ["easy"] * 4 + ["medium"] * 4 + ["hard"] * 4 + ["expert"] * 3
ALL_HUNT_T = float(os.environ.get("SIM_ALL_HUNT_T", "300"))
DEFEND_RANGE = float(os.environ.get("SIM_DEFEND_RANGE", "60"))
AIM_MULT = float(os.environ.get("SIM_AIM_MULT", "1.0"))
MEMORY = 5.0
# Observed on the real board (Sat Nov 21): the house bots ALWAYS know where the entrant is (hiding, cover, roofs
# and kiting never shook them off). Default on; SIM_OMNISCIENT=0 restores the old shared-vision model.
OMNISCIENT = os.environ.get("SIM_OMNISCIENT", "1") != "0"


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def squad(m) -> Dict[str, Any]:
    if not hasattr(m, "_squad"):
        house = [x.id for x in m.mechs if x.house]
        rnd = random.Random(m.rng.random())
        rnd.shuffle(house)
        m._squad = {"order": house, "last_known": {}}
    return m._squad


class HouseBot:
    is_house = True
    wants_match = True

    def __init__(self, hello: Dict[str, Any], match: Any, level: str):
        self.match, self.slot, self.level = match, hello["slot"], level
        self.err, self.react, self.strafe, self.pref = LEVELS[level]
        self.err *= AIM_MULT
        self.rng = random.Random(hello["seed"])
        self.target_id: Optional[int] = None
        self.target_t = 0.0
        self.side, self.side_t = 1.0, 0.0
        self.roam: Optional[List[float]] = None
        self.roam_key = None
        self.hit_by: Dict[int, float] = {}
        self.name = f"house-{level}"

    def _is_hunter(self) -> bool:
        m = self.match
        sq = squad(m)
        if m.t >= ALL_HUNT_T:
            return True
        dead = sum(1 for x in m.mechs if x.house and not x.alive)
        alive_order = [i for i in sq["order"] if m.mechs[i].alive]
        return self.slot in alive_order[: 1 + dead]

    def act(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        m, me = self.match, obs["self"]
        pos, t = me["pos"], obs["t"]
        sq = squad(m)
        act: Dict[str, Any] = {"tick": obs["tick"]}
        if obs.get("offer"):
            act["pick"] = 0
        for e in obs.get("events", []):
            if e.get("type") == "damaged" and e.get("by") is not None and e["by"] < 100:
                self.hit_by[e["by"]] = t
        entrants = [o for o in m.mechs if o.alive and not o.house]
        known = []
        for o in entrants:
            if OMNISCIENT or any(h.alive and h.house and h.seen.get(o.id, -1e9) >= m.t - MEMORY for h in m.mechs):
                sq["last_known"][o.id] = (list(o.pos), m.t)
                known.append(o)
        hunter = self._is_hunter()
        tgt = None
        chase_point = None
        if hunter:
            if known:
                tgt = min(known, key=lambda o: o.hp)              # weakest first
            elif sq["last_known"]:
                lk = min(sq["last_known"].items(), key=lambda kv: m.mechs[kv[0]].hp if m.mechs[kv[0]].alive else 1e9)
                if m.mechs[lk[0]].alive:
                    chase_point = lk[1][0]
        else:
            for o in known:
                d = math.dist(o.pos[:2], pos[:2])
                if d < DEFEND_RANGE or t - self.hit_by.get(o.id, -1e9) < 5.0:
                    tgt = o if tgt is None or d < math.dist(tgt.pos[:2], pos[:2]) else tgt
        if tgt is None or tgt.id != self.target_id:
            self.target_id = tgt.id if tgt is not None else None
            self.target_t = t
        z = obs["zone"]
        nc, nr = z["next_center"], z["next_radius"]
        key = (round(nc[0]), round(nc[1]), round(nr))
        if key != self.roam_key:
            a, d = self.rng.uniform(-math.pi, math.pi), nr * 0.6 * math.sqrt(self.rng.random())
            self.roam, self.roam_key = [nc[0] + math.cos(a) * d, nc[1] + math.sin(a) * d], key
        mv = [0.0, 0.0]
        dest = chase_point if (hunter and tgt is None and chase_point is not None) else self.roam
        dz = math.dist(pos[:2], nc)
        if dz > nr * 0.85 or not me["in_zone"]:
            dest = nc
            act["boost"] = not me["in_zone"] and me["energy"] > 20
        if dest is not None:
            dd = math.dist(pos[:2], dest[:2])
            if dd > 4:
                mv = [(dest[0] - pos[0]) / dd, (dest[1] - pos[1]) / dd]
        if tgt is not None:
            d = math.dist(tgt.pos[:2], pos[:2])
            by = math.atan2(tgt.pos[1] - pos[1], tgt.pos[0] - pos[0])
            radial = 1.0 if d > self.pref else (-0.6 if d < self.pref * 0.5 else 0.0)
            if not hunter:
                radial = min(radial, 0.0)                        # defenders do not chase
            mv = [mv[0] * 0.3 + math.cos(by) * radial, mv[1] * 0.3 + math.sin(by) * radial]
            if self.strafe:
                if t > self.side_t:
                    self.side, self.side_t = -self.side, t + self.rng.uniform(0.8, 2.0)
                mv = [mv[0] + math.cos(by + self.side * math.pi / 2) * 0.8,
                      mv[1] + math.sin(by + self.side * math.pi / 2) * 0.8]
            mz = pos[2] + me["stats"].get("muzzle_height", 7.0)
            tc = [tgt.pos[0], tgt.pos[1], tgt.pos[2] + tgt.height / 2]
            tt = math.dist([pos[0], pos[1], mz], tc) / 252.0
            px, py = tc[0] + tgt.vel[0] * tt, tc[1] + tgt.vel[1] * tt
            e = math.radians(self.err)
            yaw = math.atan2(py - pos[1], px - pos[0]) + self.rng.gauss(0, e)
            pit = math.atan2(tc[2] - mz, math.hypot(px - pos[0], py - pos[1])) + self.rng.gauss(0, e * 0.5)
            act["aim"] = [yaw, pit]
            on = abs(wrap(me["aim"][0] - yaw)) < 0.06 + e and t - self.target_t > self.react
            clear = m.los([pos[0], pos[1], mz], tc)
            fire = [False, False]
            for i, w in enumerate(me["weapons"]):
                if not w:
                    continue
                if w["kind"] == "gun":
                    fire[i] = on and clear and d < 230
                elif w["kind"] == "laser":
                    full = w.get("charge", 0) >= w["stats"]["charge"] - 0.02
                    fire[i] = clear and d < 280 and not (full and on)
                elif w["kind"] == "lightning":
                    fire[i] = d < 44 and on
            act["fire"] = fire
        else:
            act["aim"] = [me["aim"][0] + 0.5, 0.0]
            if me["weapons"][1] is None:
                ps = [p for p in obs["pickups"] if p["kind"] in ("laser", "lightning")]
                if ps:
                    p = min(ps, key=lambda p: math.dist(p["pos"][:2], pos[:2]))
                    d = math.dist(p["pos"][:2], pos[:2])
                    if d < 40:
                        mv = [(p["pos"][0] - pos[0]) / max(d, 1), (p["pos"][1] - pos[1]) / max(d, 1)]
                        if d < 3.5:
                            act["take"] = p["id"]
        n = math.hypot(*mv)
        if n > 1e-6:
            mv = [mv[0] / n, mv[1] / n]
            if not m.wm.free(pos[0] + mv[0] * 4, pos[1] + mv[1] * 4):
                for da in (0.6, -0.6, 1.2, -1.2, 1.8, -1.8):
                    a = math.atan2(mv[1], mv[0]) + da
                    if m.wm.free(pos[0] + math.cos(a) * 4, pos[1] + math.sin(a) * 4):
                        mv = [math.cos(a), math.sin(a)]
                        break
                else:
                    act["jump"] = True
                    act["boost"] = True
        act["move"] = mv
        return act


def house_factory(level: str):
    def make(hello, match):
        return HouseBot(hello, match, level)
    make.wants_match = True
    return make
