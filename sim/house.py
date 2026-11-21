"""Stand-ins for the scorer's house bots (track page: 4 easy, 4 medium, 4 hard, 3 expert; they share vision and
hunt the weakest entrant first). Their real code is unknown; these follow that description:

- shared vision: a house bot knows every mech that ANY house bot currently sees;
- target: the weakest visible entrant (non-house mech) within hunt_radius, else the nearest visible mech;
- move: inside the next circle first; then close to a preferred range of the target, strafing (hard/expert);
- aim: perfect lead plus Gaussian error by level, firing only after a reaction delay on a new target;
- loot: walk to a laser or lightning within 40 m while the slot is empty.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional

LEVELS = {
    #          aim error deg, reaction s, strafe, preferred range m, hunt radius m
    "easy":   (3.5, 0.9, False, 50.0, 220.0),
    "medium": (2.2, 0.6, False, 60.0, 260.0),
    "hard":   (1.3, 0.4, True, 70.0, 300.0),
    "expert": (0.7, 0.25, True, 80.0, 340.0),
}
FIELD = ["easy"] * 4 + ["medium"] * 4 + ["hard"] * 4 + ["expert"] * 3


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class HouseBot:
    is_house = True
    wants_match = True

    def __init__(self, hello: Dict[str, Any], match: Any, level: str):
        self.match, self.slot, self.level = match, hello["slot"], level
        self.err, self.react, self.strafe, self.pref, self.hunt = LEVELS[level]
        self.rng = random.Random(hello["seed"])
        self.target_id: Optional[int] = None
        self.target_t = 0.0
        self.side, self.side_t = 1.0, 0.0
        self.name = f"house-{level}"

    def _shared_visible(self) -> List[Any]:
        m = self.match
        out = []
        for o in m.mechs:
            if not o.alive or o.id == self.slot:
                continue
            if any(h.alive and h.house and h.seen.get(o.id, -1e9) >= m.t - 0.15 for h in m.mechs):
                out.append(o)
        return out

    def act(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        m, me = self.match, obs["self"]
        pos, t = me["pos"], obs["t"]
        act: Dict[str, Any] = {"tick": obs["tick"]}
        if obs.get("offer"):
            act["pick"] = 0
        vis = self._shared_visible()
        entrants = [o for o in vis if not o.house and math.dist(o.pos[:2], pos[:2]) < self.hunt]
        if entrants:
            tgt = min(entrants, key=lambda o: o.hp)
        elif vis:
            tgt = min(vis, key=lambda o: math.dist(o.pos[:2], pos[:2]))
            if math.dist(tgt.pos[:2], pos[:2]) > 200:
                tgt = None
        else:
            tgt = None
        if tgt is None or tgt.id != self.target_id:
            self.target_id = tgt.id if tgt is not None else None
            self.target_t = t
        z = obs["zone"]
        nc, nr = z["next_center"], z["next_radius"]
        dz = math.dist(pos[:2], nc)
        mv = [0.0, 0.0]
        if dz > nr * 0.7 or not me["in_zone"]:
            mv = [(nc[0] - pos[0]) / max(dz, 1), (nc[1] - pos[1]) / max(dz, 1)]
            act["boost"] = not me["in_zone"] and me["energy"] > 20
        if tgt is not None:
            d = math.dist(tgt.pos[:2], pos[:2])
            by = math.atan2(tgt.pos[1] - pos[1], tgt.pos[0] - pos[0])
            radial = 1.0 if d > self.pref else (-0.6 if d < self.pref * 0.5 else 0.0)
            mv = [mv[0] + math.cos(by) * radial, mv[1] + math.sin(by) * radial]
            if self.strafe:
                if t > self.side_t:
                    self.side, self.side_t = -self.side, t + self.rng.uniform(0.8, 2.0)
                mv = [mv[0] + math.cos(by + self.side * math.pi / 2) * 0.8,
                      mv[1] + math.sin(by + self.side * math.pi / 2) * 0.8]
            # aim: lead the target with our gun speed, plus error
            mz = pos[2] + me["stats"].get("muzzle_height", 7.0)
            sp = 252.0
            tc = [tgt.pos[0], tgt.pos[1], tgt.pos[2] + tgt.height / 2]
            tt = math.dist([pos[0], pos[1], mz], tc) / sp
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
                elif w["kind"] == "mortar":
                    fire[i] = False
            act["fire"] = fire
        else:
            act["aim"] = [me["aim"][0] + 0.5, 0.0]
            # loot a better weapon nearby
            if me["weapons"][1] is None:
                ps = [p for p in obs["pickups"] if p["kind"] in ("laser", "lightning")]
                if ps:
                    p = min(ps, key=lambda p: math.dist(p["pos"][:2], pos[:2]))
                    d = math.dist(p["pos"][:2], pos[:2])
                    if d < 40:
                        mv = [(p["pos"][0] - pos[0]) / max(d, 1), (p["pos"][1] - pos[1]) / max(d, 1)]
                        if d < 3.5:
                            act["take"] = p["id"]
        # walls: if blocked ahead, sidestep
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
