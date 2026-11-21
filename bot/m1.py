"""M1: minimal cube-first bot (mechfight/1). One file, no map, a few ms per decision.

Priority each decision: events/offers -> zone (outside, or the shrink is coming and we are near the edge)
-> fight (attacked in the last 4 s and visible, or a mech within FIGHT_RANGE) with a heal break when 2+ mechs
hit us below 50 % HP -> farm (cube, laser/lightning, drone from 50-110 m, crate from <= 45 m) -> roam inside the
next circle sweeping the torso. Always: face the last damage bearing when there is nothing to shoot, unstick.
"""
import math
import random

FIGHT_RANGE = 120.0       # M2 (was 85)
FARM_UNTIL = 1e9          # M3: 90.0
UPGRADE_PREF = ["armor", "plating", "nanites", "gun_damage", "gun_rate"]


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def d2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class M1Bot:
    name = "goonies-m1"

    def __init__(self, hello):
        self.rng = random.Random(hello.get("seed", 0))
        self.hit_by = {}            # mech id -> last time it damaged us
        self.last_dmg = (-1e9, None, None)   # (t, by, bearing)
        self.tgt_id, self.tgt_seen = None, -1e9
        self.side, self.side_until = 1.0, 0.0
        self.jump_t = 0.0
        self.heal = False
        self.roam = None
        self.slow_since, self.turned = None, False
        self.detour_until, self.detour_yaw = -1e9, 0.0
        self.sweep = 0.0
        self.mode = "START"

    # ------------------------------------------------------------------ helpers
    def _aim(self, me, tgt, kind, speed):
        p = me["pos"]
        mz = p[2] + me["stats"].get("muzzle_height", 7.0)
        dz = {"mech": 4.5, "npc": 1.75, "crate": 1.2}[kind]
        tp = tgt["pos"]
        v = tgt.get("vel", [0.0, 0.0, 0.0]) if kind != "crate" else [0.0, 0.0, 0.0]
        pt = [tp[0], tp[1], tp[2] + dz]
        if speed:
            for _ in range(3):
                t = math.dist([p[0], p[1], mz], pt) / speed
                pt = [tp[0] + v[0] * t, tp[1] + v[1] * t, tp[2] + dz + v[2] * t]
        yaw = math.atan2(pt[1] - p[1], pt[0] - p[0])
        pitch = math.atan2(pt[2] - mz, math.hypot(pt[0] - p[0], pt[1] - p[1]))
        return yaw, pitch, math.dist([p[0], p[1], mz], pt)

    def _shoot(self, me, tgt, kind, act):
        """Aim and fire every weapon at tgt. Returns the distance."""
        ws = me["weapons"]
        gun = next((w for w in ws if w and w["kind"] == "gun"), None)
        speed = gun["stats"].get("speed", 252.0) if gun else 252.0
        yaw, pitch, d = self._aim(me, tgt, kind, speed)
        laser = any(w and w["kind"] == "laser" for w in ws)
        if laser and d < 280:
            ly, lp, _ = self._aim(me, tgt, kind, None)      # hitscan: no lead
        else:
            ly, lp = yaw, pitch
        cy, cp = me["aim"]
        fire = [False, False]
        for i, w in enumerate(ws):
            if not w:
                continue
            k = w["kind"]
            if k == "gun":
                err = abs(wrap(cy - yaw)) + abs(cp - pitch)
                fire[i] = err < 0.05 and d < 90 and w.get("ammo", 1) > 0
                if w.get("ammo", 1) <= 0 and w.get("reload", 0) <= 0:
                    act["reload"] = True
            elif k == "laser":
                err = abs(wrap(cy - ly)) + abs(cp - lp)
                ch = w.get("charge", 0.0)
                full = ch >= w["stats"].get("charge", 0.75)
                if d < 280:
                    fire[i] = (not full and err < 0.4) or (full and err >= 0.025)
            elif k == "lightning":
                fire[i] = d < 44 and abs(wrap(cy - yaw)) < 0.25
            elif k == "mortar":
                fire[i] = False
        # aim with the gun's lead unless only the laser can reach
        if laser and (d >= 90 or not gun):
            act["aim"] = [ly, lp]
        else:
            act["aim"] = [yaw, pitch]
        act["fire"] = fire
        return d

    def _go(self, me, goal, act, boost=False):
        p = me["pos"]
        d = d2(p, goal)
        if d < 1.5:
            act["move"] = [0.0, 0.0]
            return
        act["move"] = [(goal[0] - p[0]) / d, (goal[1] - p[1]) / d]
        act["boost"] = boost and me["energy"] > 25

    # ------------------------------------------------------------------ decision
    def act(self, obs):
        me, t = obs["self"], obs["t"]
        self._now = t
        p = me["pos"]
        act = {"tick": obs["tick"], "move": [0.0, 0.0], "fire": [False, False], "boost": False}
        # 1. events and offers
        for e in obs.get("events", []):
            if e.get("type") == "damaged":
                by = e.get("by")
                if by is not None and by < 100:
                    self.hit_by[by] = t
                self.last_dmg = (t, by, e.get("bearing"))
        off = obs.get("offer")
        if off:
            ch = off["choices"]
            rank = {k: i for i, k in enumerate(UPGRADE_PREF)}
            best = min(range(len(ch)), key=lambda i: rank.get(ch[i]["id"], 99))
            act["pick"] = best if ch[best]["id"] in rank else 0

        mechs = [m for m in obs["mechs"] if m["kind"] == "mech"]
        npcs = [m for m in obs["mechs"] if m["kind"] == "npc"]
        z = obs["zone"]
        nc, nr = z["next_center"], z["next_radius"]
        dz = d2(p, nc)
        hp_frac = me["hp"] / max(me["max_hp"], 1.0)

        # 2. target choice (sticky)
        vis = {m["id"]: m for m in mechs}
        cur = vis.get(self.tgt_id)
        if cur is not None:
            self.tgt_seen = t
        elif self.tgt_id is not None and t - self.tgt_seen > 2.0:
            self.tgt_id = None
        cands = [m for m in mechs if t - self.hit_by.get(m["id"], -1e9) < 4.0 or d2(m["pos"], p) < FIGHT_RANGE]
        weak = [m for m in cands if m.get("hp", 1400) < 0.4 * m.get("max_hp", 1400) and m is not cur]
        if weak and (cur is None or weak[0].get("hp", 0) < cur.get("hp", 0)):
            cur = min(weak, key=lambda m: m.get("hp", 0))
        elif cur is None and cands:
            cur = min(cands, key=lambda m: (0 if t - self.hit_by.get(m["id"], -1e9) < 4.0 else 1, d2(m["pos"], p)))
        if cur is not None and cur not in cands and self.tgt_id != cur["id"]:
            cur = None
        if cur is not None:
            self.tgt_id, self.tgt_seen = cur["id"], t

        # heal break: 2+ mechs hit us in the last 3 s and HP < 50 %; ends after 5 s without damage
        attackers = [i for i, tt in self.hit_by.items() if t - tt < 3.0]
        if len(attackers) >= 2 and hp_frac < 0.5:
            self.heal = True
        if self.heal and t - self.last_dmg[0] >= 5.0:
            self.heal = False

        outside = not me.get("in_zone", True)
        shrink_soon = z["shrink_start"] - t < 15.0 and dz > nr - 20.0 and nr > 1.0
        if outside or shrink_soon:
            # 3. zone first; shoot on the way if someone is close
            self.mode = "ZONE"
            self._go(me, nc, act, boost=True)
            if cur is not None:
                self._shoot(me, cur, "mech", act)
            else:
                act["aim"] = [math.atan2(act["move"][1], act["move"][0]) if any(act["move"]) else me["aim"][0], 0.0]
        elif cur is not None and self.heal:
            self.mode = "HEAL"
            by = math.atan2(cur["pos"][1] - p[1], cur["pos"][0] - p[0])
            away = by + math.pi + self.side * 0.5
            act["move"] = [math.cos(away), math.sin(away)]
            act["boost"] = me["energy"] > 25
            self._shoot(me, cur, "mech", act)
        elif cur is not None:
            self.mode = "FIGHT"
            d = self._shoot(me, cur, "mech", act)
            self._strafe(me, cur, act, d, 35.0, 70.0)
        else:
            self._farm(obs, me, npcs, act, t, nc, nr)

        # 5. nothing to shoot but hit lately: face the damage
        if "aim" not in act or (cur is None and self.mode in ("ROAM",)):
            if t - self.last_dmg[0] < 3.0 and self.last_dmg[2] is not None:
                act["aim"] = [self.last_dmg[2], 0.0]
            elif "aim" not in act:
                self.sweep = wrap(me["aim"][0] + 0.6)
                act["aim"] = [self.sweep, 0.0]
        self._unstick(me, act, t)
        return act

    def _strafe(self, me, tgt, act, d, lo, hi):
        t = self._t
        p = me["pos"]
        if t >= self.side_until:
            self.side = -self.side
            self.side_until = t + self.rng.uniform(0.5, 1.4)
        by = math.atan2(tgt["pos"][1] - p[1], tgt["pos"][0] - p[0])
        s = by + self.side * math.pi / 2
        mx, my = math.cos(s), math.sin(s)
        if d > hi:
            mx, my = mx + math.cos(by), my + math.sin(by)
        elif d < lo:
            mx, my = mx - math.cos(by), my - math.sin(by)
        n = math.hypot(mx, my) or 1.0
        act["move"] = [mx / n, my / n]
        if me["energy"] > 35 and t >= self.jump_t and me.get("grounded", True):
            act["jump"] = True
            self.jump_t = t + self.rng.uniform(1.5, 3.5)

    def _farm(self, obs, me, npcs, act, t, nc, nr):
        p = me["pos"]
        farming = t < FARM_UNTIL
        ws = me["weapons"]
        held = {w["kind"] for w in ws if w}
        if farming:
            cubes = [c for c in obs.get("cubes", []) if d2(c["pos"], p) < 120]
            if cubes:
                c = min(cubes, key=lambda c: d2(c["pos"], p))
                self.mode = "CUBE"
                self._go(me, c["pos"], act, boost=d2(c["pos"], p) > 40)
                return
            want = [q for q in obs.get("pickups", []) if d2(q["pos"], p) < 130 and
                    (q["kind"] == "laser" and "laser" not in held or
                     q["kind"] == "lightning" and (len(ws) < 2 or ws[1] is None))]
            if want:
                q = min(want, key=lambda q: d2(q["pos"], p))
                self.mode = "PICKUP"
                self._go(me, q["pos"], act, boost=d2(q["pos"], p) > 40)
                if d2(q["pos"], p) < 3.8:
                    act["take"] = q["id"]
                    if len(ws) > 1 and ws[1] is not None:
                        act["drop"] = 1
                return
            drones = [n for n in npcs if d2(n["pos"], p) < 170]
            if drones:
                n = min(drones, key=lambda n: d2(n["pos"], p))
                self.mode = "DRONE"
                d = self._shoot(me, n, "npc", act)
                self._strafe(me, n, act, d2(n["pos"], p), 50.0, 85.0)
                return
            crates = [c for c in obs.get("crates", []) if d2(c["pos"], p) < 150 and abs(c["pos"][2] - p[2]) < 3.0]
            if crates:
                c = min(crates, key=lambda c: d2(c["pos"], p))
                self.mode = "CRATE"
                self._shoot(me, c, "crate", act)
                if d2(c["pos"], p) > 40:
                    self._go(me, c["pos"], act)
                return
        self.mode = "ROAM"
        if self.roam is None or d2(p, self.roam) < 6 or d2(self.roam, nc) > nr * 0.7:
            a, r = self.rng.uniform(-math.pi, math.pi), nr * 0.5 * math.sqrt(self.rng.random())
            self.roam = (nc[0] + math.cos(a) * r, nc[1] + math.sin(a) * r)
        self._go(me, self.roam, act)

    def _unstick(self, me, act, t):
        mv = act.get("move", [0.0, 0.0])
        sp = math.hypot(me["vel"][0], me["vel"][1])
        if t < self.detour_until:
            act["move"] = [math.cos(self.detour_yaw), math.sin(self.detour_yaw)]
            return
        if math.hypot(*mv) > 0.5 and sp < 2.0:
            if self.slow_since is None:
                self.slow_since = t
            elif t - self.slow_since > 2.5:
                self.detour_yaw = math.atan2(mv[1], mv[0]) + self.side * math.pi / 2
                self.detour_until = t + 1.5
                self.slow_since = None
            elif t - self.slow_since > 0.5:
                act["jump"] = True
                act["boost"] = me["energy"] > 5
        else:
            self.slow_since = None

    @property
    def _t(self):
        return self._now
