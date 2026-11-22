"""A simplified mechfight/1 match, in-process, standard library only.

Built from kit/protocol.md and the full rule set in the kit's recorded `hello` (kit/check/stream.jsonl.gz). It
is NOT the real server: it exists to compare bot versions without spending submissions. What it models:

- 20 Hz ticks, a decision every 2 ticks; bots get the same obs dicts the protocol defines and answer actions.
- Movement on the real map (3 m grid from arena/v2): walk / boost / jump / jet with energy, gravity, walls that
  stop you unless your feet clear them, standing on roofs, the 50 degree slope rule (as walls).
- Aim slewing at turn_rate / pitch_rate; shots leave along the actual aim.
- Gun (bullets with travel, spread, magazine, reload), laser (hold to charge, release; hitscan), lightning
  (nearest target in a cone, chains), mortar (ballistic shell, splash, knock-back skipped).
- Rear armour x1.5 outside the target's 180 degree front arc, cube damage/HP scaling, armour upgrades,
  regen after 5 s, zone phases with damage, death drops, cubes, crates, floor loot, upgrade offers.
- Vision (near range all round, 200 m in the 120 degree cone, line of sight vs buildings; canopy ignored),
  5 s memory, sounds with bearing noise and near/mid/far, events (damaged, hit, kill, pickup, took, upgrade).
- NPC drones that shoot mechs inside 45 m (or whoever hit them) and drop 2 cubes.
Not modelled: supply drops, mortar concussion/knock-back, laser cook-off, lightning short, eaves/bridges,
mech-mech pushing, trees. Placement: death order; at 480 s survivors are ranked by HP.
"""
from __future__ import annotations

import gc
import math
import os
import random
import time

# Measurement only: pause Python's garbage collector while an entrant decides, so a collection of the whole
# simulation's objects (which the real bot, alone in its own process with gc.freeze(), never pays) is not
# charged to the bot's response time.
SIM_GC_OFF = os.environ.get("SIM_GC_OFF", "0") == "1"
from typing import Any, Callable, Dict, List, Optional, Tuple

DT = 0.05


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class Mech:
    def __init__(self, mid: int, pos, rules, controller, name: str):
        m = rules["mech"]
        self.id, self.name, self.ctrl = mid, name, controller
        self.pos = list(pos)
        self.vel = [0.0, 0.0, 0.0]
        self.aim = [random.uniform(-math.pi, math.pi), 0.0]
        self.stats = dict(m)
        self.wstats: Dict[str, Dict[str, float]] = {k: dict(v) for k, v in rules["weapons"].items()}
        self.hp = self.max_hp = float(m["hp"])
        self.energy = float(m["energy"])
        self.cubes = 0
        self.upgrades: List[str] = []
        self.slots: List[Optional[Dict[str, Any]]] = [self._weapon("gun"), None]
        self.alive = True
        self.place: Optional[int] = None
        self.kills = 0
        self.cmd: Dict[str, Any] = {}
        self.last_combat = -1e9
        self.last_spend = -1e9
        self.grounded = True
        self.seen: Dict[int, float] = {}
        self.events: List[Dict[str, Any]] = []
        self.sounds: List[Dict[str, Any]] = []
        self.beams: List[Dict[str, Any]] = []
        self.step_t = 0.0
        self.offers: List[List[str]] = []
        self.offer_id = 0
        self.offer_expires = 0.0
        self.next_threshold = 0
        self.decide_ms: List[float] = []
        self.late = 0
        self.house = False
        self.death_t: Optional[float] = None
        self.death_cause: Optional[str] = None
        self.death_by: Optional[str] = None
        self.death_mode: Optional[str] = None
        self.dmg_log: List[Tuple[float, Optional[int], str, float, Optional[float]]] = []
        self.hp_hist: List[Tuple[float, float, float]] = []
        self.min_hp_by_entrant = 1.0
        self.entrant_last_hit = -1e9
        self.upg_t: List[Tuple[float, str]] = []
        self.laser_t: Optional[float] = None
        self.mode_hist: List[Tuple[float, Optional[str]]] = []
        self.shots: Dict[str, int] = {}
        self.hits: Dict[str, int] = {}
        self.dmg_dealt = 0.0
        self.dmg_taken = 0.0
        self.shot_d: List[float] = []     # distance to the nearest enemy at each gun shot
        self.hit_d: List[float] = []      # distance at each gun hit on a mech
        self.boosting = False
        self.shot_cls: Dict[str, int] = {}  # (weapon, target motion) -> shots aimed at the nearest enemy
        self.hit_cls: Dict[str, int] = {}   # ... and hits on it
        self.first_hit: Dict[int, float] = {}   # attacker id -> time of its first hit on us
        self.ttk: List[float] = []        # our kills: seconds from our first hit to its death

    def _weapon(self, kind: str) -> Dict[str, Any]:
        w = {"kind": kind, "cooldown": 0.0}
        if kind == "gun":
            w.update(ammo=int(self.wstats["gun"]["mag"]), reload=0.0)
        if kind == "laser":
            w["charge"] = 0.0
        return w

    @property
    def size(self) -> float:
        return 1 + 0.05 * self.cubes

    @property
    def radius(self) -> float:
        return self.stats["radius"] * self.size

    @property
    def height(self) -> float:
        return self.stats["height"] * self.size

    def dmg_mult(self, rules) -> float:
        c = rules["cubes"]
        return 1 + c["damage_per_cube"] * min(self.cubes, c["stat_cap"])


class Match:
    def __init__(self, wm, rules: Dict[str, Any], entrants: List[Tuple[str, Callable]], seed: int,
                 map_dir: str, house_factory: Optional[Callable] = None, log: bool = False):
        self.wm, self.rules, self.rng = wm, rules, random.Random(seed)
        random.seed(seed)
        self.t, self.tick = 0.0, 0
        self.map_dir = map_dir
        self.log = log
        self.mechs: List[Mech] = []
        self.npcs: List[Dict[str, Any]] = []
        self.crates: List[Dict[str, Any]] = []
        self.cubes: List[Dict[str, Any]] = []
        self.pickups: List[Dict[str, Any]] = []
        self.bullets: List[Dict[str, Any]] = []
        self.shells: List[Dict[str, Any]] = []
        self.next_id = {"crate": 1000, "cube": 5000, "pickup": 8000, "proj": 1}
        self.deaths: List[Tuple[int, int]] = []   # (tick, mech id)
        self.telemetry = {"drone_kills": 0}
        self._setup_zone()
        spawns = self._spawns(len(entrants))
        for i, ((name, factory), p) in enumerate(zip(entrants, spawns)):
            m = Mech(i, p, rules, None, name)
            self.mechs.append(m)
            hello = {"type": "hello", "protocol": "mechfight/1", "slot": i, "seed": self.rng.randrange(1 << 30),
                     "map": {"dir": map_dir, "files": ["v2/world.json", "v2/terrain.i16"]}, "config": rules}
            m.ctrl = factory(hello, self) if getattr(factory, "wants_match", False) else factory(hello)
            m.house = getattr(m.ctrl, "is_house", False)
        self._setup_world()

    # ------------------------------------------------------------------ setup
    def _free_point(self, inside: Optional[Tuple[Tuple[float, float], float]] = None, tries: int = 400):
        wm = self.wm
        for _ in range(tries):
            x = self.rng.uniform(wm.minx + 30, wm.maxx - 30)
            y = self.rng.uniform(wm.miny + 30, wm.maxy - 30)
            if inside is not None and math.hypot(x - inside[0][0], y - inside[0][1]) > inside[1]:
                continue
            if wm.free(x, y):
                return [x, y, wm.ground(x, y)]
        return None

    def _spawns(self, n: int):
        z = self.rules["zone"]
        c, r = z["start_center"], z["start_radius"] * self.rules["match"]["spawn_zone_fraction"]
        sep = self.rules["match"]["spawn_min_separation"]
        pts: List[List[float]] = []
        while len(pts) < n:
            p = self._free_point(((c[0], c[1]), r))
            if p is None:
                continue
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) > sep for q in pts):
                pts.append(p)
            elif sep > 40:
                sep *= 0.995
        return pts

    def _setup_zone(self):
        z = self.rules["zone"]
        self.phases = z["phases"]
        self.zc, self.zr = list(z["start_center"]), float(z["start_radius"])
        self.phase = 0
        self.phase_start = 0.0
        self._pick_next()

    def _pick_next(self):
        if self.phase >= len(self.phases):
            self.nc, self.nr = list(self.zc), 0.0
            return
        nr = self.phases[self.phase]["radius"]
        slack = max(self.zr - nr, 0.0)
        for _ in range(200):
            a, d = self.rng.uniform(-math.pi, math.pi), slack * math.sqrt(self.rng.random())
            x, y = self.zc[0] + math.cos(a) * d, self.zc[1] + math.sin(a) * d
            if self.wm.minx + nr * 0.3 < x < self.wm.maxx - nr * 0.3 and self.wm.miny + nr * 0.3 < y < self.wm.maxy - nr * 0.3:
                break
        self.nc, self.nr = [x, y], float(nr)

    def _setup_world(self):
        r = self.rules
        for i in range(r["npc"]["count"]):
            p = self._free_point()
            self.npcs.append({"id": 100 + i, "pos": p, "home": list(p), "hp": float(r["npc"]["hp"]),
                              "cool": self.rng.uniform(0, 1), "target": None, "target_t": -1e9})
        for _ in range(r["crates"]["count"]):
            p = self._free_point()
            self.crates.append({"id": self._nid("crate"), "pos": p, "hp": float(r["crates"]["hp"])})
        kinds = [k for k, w in r["loot"]["weights"].items() for _ in range(int(w))]
        for _ in range(r["loot"]["floor_count"]):
            self._drop_pickup(self.rng.choice(kinds), self._free_point())

    def _nid(self, k: str) -> int:
        self.next_id[k] += 1
        return self.next_id[k]

    def _drop_pickup(self, kind, pos, w=None):
        if pos is None:
            return
        self.pickups.append({"id": self._nid("pickup"), "kind": kind, "pos": list(pos), "w": w})

    # ------------------------------------------------------------------ zone
    def zone_now(self):
        ph = self.phases[self.phase] if self.phase < len(self.phases) else None
        if ph is None:
            return (self.zc, 0.0)
        s = self.phase_start + ph["hold_s"]
        e = s + ph["shrink_s"]
        if self.t <= s:
            return self.zc, self.zr
        f = min((self.t - s) / max(e - s, 1e-6), 1.0)
        return ([self.zc[0] + (self.nc[0] - self.zc[0]) * f, self.zc[1] + (self.nc[1] - self.zc[1]) * f],
                self.zr + (self.nr - self.zr) * f)

    def _zone_obs(self):
        ph = self.phases[min(self.phase, len(self.phases) - 1)]
        s = self.phase_start + ph["hold_s"]
        return {"center": list(self.zc), "radius": self.zr, "next_center": list(self.nc), "next_radius": self.nr,
                "shrink_start": s, "shrink_end": s + ph["shrink_s"], "dps": ph["dps"]}

    def _zone_step(self):
        if self.phase >= len(self.phases):
            return
        ph = self.phases[self.phase]
        if self.t >= self.phase_start + ph["hold_s"] + ph["shrink_s"]:
            self.zc, self.zr = list(self.nc), self.nr
            self.phase += 1
            self.phase_start = self.t
            self._pick_next()

    # ------------------------------------------------------------------ geometry helpers
    def support(self, x, y, z):
        """Height of what is under (x, y) for feet at z: a roof we are above, else the ground."""
        k = self.wm.idx(x, y)
        roof = self.wm.roof[k]
        if self.wm.blocked[k] and roof > -1e8 and z >= roof - 0.6:
            return roof
        return self.wm.gnd[k]

    def passable(self, x, y, z, step):
        k = self.wm.idx(x, y)
        if not self.wm.blocked[k]:
            return True
        roof = self.wm.roof[k]
        return roof > -1e8 and z >= roof - step

    def los(self, a, b):
        return self.wm.los(a, b, step=3.0)

    # ------------------------------------------------------------------ main loop
    def run(self, max_t: Optional[float] = None) -> Dict[int, int]:
        dur = max_t or self.rules["match"]["duration_s"]
        while self.t < dur and sum(1 for m in self.mechs if m.alive) > 1:
            if self.tick % 2 == 0:
                self._decide()
            self._step()
            self.tick += 1
            self.t = self.tick * DT
        alive = sorted((m for m in self.mechs if m.alive), key=lambda m: -m.hp)
        for i, m in enumerate(alive):
            m.place = i + 1
        return {m.id: m.place for m in self.mechs}

    # ------------------------------------------------------------------ decisions
    def _decide(self):
        vis_items = self.tick % 8 == 0
        if vis_items:
            self._item_vis = {}
        alive_n = sum(1 for m in self.mechs if m.alive)
        for m in self.mechs:
            if not m.alive:
                continue
            self._offer_timeout(m)
            obs = self._obs(m, alive_n, vis_items)
            gc_off = SIM_GC_OFF and not m.house
            if gc_off:
                gc.disable()
            t0 = time.perf_counter()
            try:
                act = m.ctrl.act(obs) or {}
            except Exception as e:  # a crashing bot idles (protocol section 2)
                if self.log:
                    print(f"{m.name} act() raised {e!r}")
                m.crashes = getattr(m, "crashes", 0) + 1
                act = {}
            ms = (time.perf_counter() - t0) * 1000
            if gc_off:
                gc.enable()
            if not m.house:
                m.decide_ms.append(ms)
            m.events, m.sounds, m.beams = [], [], []
            if not m.house:
                pl = getattr(m.ctrl, "last_plan", None)
                m.mode_hist.append((self.t, getattr(pl, "mode", None) or getattr(m.ctrl, "mode", None)))
                m.hp_hist.append((self.t, m.hp, m.energy))
                if len(m.hp_hist) > 200:
                    del m.hp_hist[:50]
            self._apply(m, act)

    def _apply(self, m: Mech, act):
        c = m.cmd
        for k in ("move", "boost", "aim"):
            if k in act:
                c[k] = act[k]
        c["jump"] = bool(act.get("jump"))
        c["fire"] = list(act.get("fire") or [False, False])
        if act.get("reload"):
            g = m.slots[0]
            if g and g["kind"] == "gun" and g["reload"] <= 0 and g["ammo"] < m.wstats["gun"]["mag"]:
                g["reload"] = m.wstats["gun"]["reload"]
                self._sound(m.pos, "reload", m.id)
        if "pick" in act and m.offers:
            ch = m.offers.pop(0)
            i = int(act["pick"]) if 0 <= int(act["pick"]) < len(ch) else 0
            self._upgrade(m, ch[i])
        if "take" in act:
            self._take(m, int(act["take"]), act.get("drop"))
        elif "drop" in act and act["drop"] in (0, 1) and m.slots[int(act["drop"])]:
            w = m.slots[int(act["drop"])]
            m.slots[int(act["drop"])] = None
            self._drop_pickup(w["kind"], m.pos, w)

    def _take(self, m: Mech, pid: int, drop):
        p = next((p for p in self.pickups if p["id"] == pid), None)
        if p is None:
            m.events.append({"type": "take_failed", "id": pid, "reason": "gone"})
            return
        if math.hypot(p["pos"][0] - m.pos[0], p["pos"][1] - m.pos[1]) > self.rules["loot"]["pickup_radius"] \
                or abs(p["pos"][2] - m.pos[2]) > 4:
            m.events.append({"type": "take_failed", "id": pid, "reason": "range"})
            return
        if any(w and w["kind"] == p["kind"] for w in m.slots):
            m.events.append({"type": "take_failed", "id": pid, "reason": "have"})
            return
        slot = 1 if m.slots[1] is None else (0 if m.slots[0] is None else (int(drop) if drop in (0, 1) else None))
        if slot is None:
            m.events.append({"type": "take_failed", "id": pid, "reason": "full"})
            return
        old = m.slots[slot]
        if old is not None:
            self._drop_pickup(old["kind"], m.pos, old)
            m.events.append({"type": "dropped", "id": self.next_id["pickup"], "kind": old["kind"], "slot": slot})
        w = p["w"] or m._weapon(p["kind"])
        w["cooldown"] = max(w.get("cooldown", 0.0), self.rules["loot"]["equip_s"],
                            m.wstats[p["kind"]].get("cooldown", 0.0))
        m.slots[slot] = w
        if p["kind"] == "laser" and m.laser_t is None:
            m.laser_t = self.t
        self.pickups.remove(p)
        m.events.append({"type": "took", "id": pid, "kind": p["kind"], "slot": slot})

    # ------------------------------------------------------------------ upgrades
    def _maybe_offer(self, m: Mech):
        th = self.rules["cubes"]["upgrade_thresholds"]
        while m.next_threshold < len(th) and m.cubes >= th[m.next_threshold]:
            m.next_threshold += 1
            held = {w["kind"] for w in m.slots if w}
            ok = [u for u in self.rules["upgrades"] if m.upgrades.count(u["id"]) < u["max"]
                  and (u.get("requires") is None or u["requires"] in held)]
            if ok:
                m.offers.append([u["id"] for u in self.rng.sample(ok, min(3, len(ok)))])
                if len(m.offers) == 1:
                    m.offer_expires = self.t + self.rules["bot"]["offer_timeout_s"]

    def _offer_timeout(self, m: Mech):
        if m.offers and self.t > m.offer_expires:
            self._upgrade(m, m.offers.pop(0)[0])
        if m.offers and m.offer_expires < self.t:
            m.offer_expires = self.t + self.rules["bot"]["offer_timeout_s"]

    def _upgrade(self, m: Mech, uid: str):
        u = next(u for u in self.rules["upgrades"] if u["id"] == uid)
        for e in u["effects"]:
            grp, key = e["path"].split(".", 1)
            if grp == "mech":
                tgt = m.stats
            else:
                tgt = m.wstats[key.split(".")[0]]
                key = key.split(".", 1)[1]
            if "mul" in e:
                tgt[key] = tgt.get(key, 0) * e["mul"]
            if "add" in e:
                tgt[key] = tgt.get(key, 0) + e["add"]
            if key == "hp":
                gain = tgt[key] * (1 + self.rules["cubes"]["hp_per_cube"] * min(m.cubes, 10)) - m.max_hp
                m.max_hp += gain
                m.hp += max(gain, 0)
        m.upgrades.append(uid)
        m.upg_t.append((round(self.t, 1), uid))
        m.events.append({"type": "upgrade", "id": uid})
        if m.offers:
            m.offer_expires = self.t + self.rules["bot"]["offer_timeout_s"]

    # ------------------------------------------------------------------ observation
    def _sees(self, m: Mech, p, top) -> bool:
        v = self.rules["vision"]
        eye = [m.pos[0], m.pos[1], m.pos[2] + m.stats["eye_height"] * m.size]
        d = math.hypot(p[0] - eye[0], p[1] - eye[1])
        near = v["near_range"] + m.stats.get("near_range_bonus", 0)
        rng = v["range"] + m.stats.get("vision_bonus", 0)
        if d > rng:
            return False
        if d > near:
            if abs(wrap(math.atan2(p[1] - eye[1], p[0] - eye[0]) - m.aim[0])) > math.radians(v["fov_deg"]) / 2:
                return False
        return self.los(eye, [p[0], p[1], p[2] + top * 0.5]) or self.los(eye, [p[0], p[1], p[2] + top])

    def _obs(self, m: Mech, alive_n: int, vis_items: bool) -> Dict[str, Any]:
        t = self.t
        mem = self.rules["vision"]["memory_s"]
        mechs = []
        for o in self.mechs:
            if o is m or not o.alive:
                continue
            if math.hypot(o.pos[0] - m.pos[0], o.pos[1] - m.pos[1]) < 230 and self._sees(m, o.pos, o.height):
                m.seen[o.id] = t
            if t - m.seen.get(o.id, -1e9) <= mem:
                mechs.append({"id": o.id, "kind": "mech", "pos": list(o.pos), "vel": list(o.vel), "aim": list(o.aim),
                              "hp": round(o.hp, 1), "max_hp": round(o.max_hp, 1), "cubes": o.cubes,
                              "weapons": [w["kind"] for w in o.slots if w],
                              "charging": any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in o.slots)})
        for n in self.npcs:
            if n["hp"] <= 0:
                continue
            if math.hypot(n["pos"][0] - m.pos[0], n["pos"][1] - m.pos[1]) < 200 and self._sees(m, n["pos"], 3.5):
                m.seen[n["id"]] = t
            if t - m.seen.get(n["id"], -1e9) <= mem:
                mechs.append({"id": n["id"], "kind": "npc", "pos": list(n["pos"]), "vel": [0.0, 0.0, 0.0],
                              "aim": [0.0, 0.0], "hp": n["hp"], "max_hp": self.rules["npc"]["hp"]})
        if vis_items or m.id not in getattr(self, "_item_vis", {}):
            def vis(lst, top):
                return [x["id"] for x in lst if math.hypot(x["pos"][0] - m.pos[0], x["pos"][1] - m.pos[1]) < 120
                        and self._sees(m, x["pos"], top)]
            self._item_vis = getattr(self, "_item_vis", {})
            self._item_vis[m.id] = (set(vis(self.crates, 2.4)), set(vis(self.cubes, 0.5)), set(vis(self.pickups, 0.5)))
        vc, vq, vp = self._item_vis[m.id]
        sw = []
        for i, w in enumerate(m.slots):
            if w is None:
                sw.append(None)
                continue
            d = {"kind": w["kind"], "cooldown": round(max(w["cooldown"], 0.0), 3), "stats": dict(m.wstats[w["kind"]])}
            if w["kind"] == "gun":
                d.update(ammo=w["ammo"], reload=round(max(w["reload"], 0.0), 3))
            if w["kind"] == "laser":
                d["charge"] = round(w.get("charge", 0.0), 3)
            sw.append(d)
        projs = [{"id": b["id"], "kind": b["kind"], "pos": list(b["pos"]), "vel": list(b["vel"])}
                 for b in self.bullets + self.shells if b["owner"] != m.id
                 and math.hypot(b["pos"][0] - m.pos[0], b["pos"][1] - m.pos[1]) < 120]
        offer = None
        if m.offers:
            offer = {"id": m.offer_id, "expires": m.offer_expires,
                     "choices": [{"id": u, "name": u, "desc": u} for u in m.offers[0]]}
        (cx, cy), cr = self.zone_now()
        st = dict(m.stats)
        st["muzzle_height"] = m.stats["muzzle_height"] * m.size
        st["eye_height"] = m.stats["eye_height"] * m.size
        return {
            "type": "obs", "tick": self.tick, "t": round(self.t, 2), "alive": alive_n,
            "self": {"id": m.id, "pos": list(m.pos), "vel": list(m.vel), "aim": list(m.aim), "hp": round(m.hp, 1),
                     "max_hp": round(m.max_hp, 1), "energy": round(m.energy, 1), "max_energy": m.stats["energy"],
                     "grounded": m.grounded, "cubes": m.cubes, "upgrades": list(m.upgrades), "weapons": sw,
                     "in_zone": math.hypot(m.pos[0] - cx, m.pos[1] - cy) <= cr, "stats": st},
            "mechs": mechs, "projectiles": projs,
            "crates": [{"id": c["id"], "pos": list(c["pos"]), "hp": c["hp"]} for c in self.crates if c["id"] in vc],
            "cubes": [{"id": c["id"], "pos": list(c["pos"])} for c in self.cubes if c["id"] in vq],
            "pickups": [{"id": p["id"], "kind": p["kind"], "pos": list(p["pos"])} for p in self.pickups if p["id"] in vp],
            "sounds": list(m.sounds), "beams": list(m.beams), "events": list(m.events), "drops": [],
            "zone": self._zone_obs(), "offer": offer,
        }

    # ------------------------------------------------------------------ sounds
    def _sound(self, p, kind, src_id):
        rng = self.rules["sound"]["range"].get(kind, 100)
        for m in self.mechs:
            if not m.alive or m.id == src_id:
                continue
            d = math.hypot(p[0] - m.pos[0], p[1] - m.pos[1])
            if d > rng:
                continue
            noise = math.radians(self.rules["sound"]["bearing_noise_deg"]) * m.stats.get("hearing", 1)
            b = math.atan2(p[1] - m.pos[1], p[0] - m.pos[0]) + self.rng.gauss(0, noise)
            dist = "near" if d < 60 else ("mid" if d < 160 else "far")
            m.sounds.append({"kind": kind, "bearing": round(wrap(b), 3), "dist": dist, "age": 0.0})

    # ------------------------------------------------------------------ physics
    def _step(self):
        r = self.rules
        self._zone_step()
        (cx, cy), cr = self.zone_now()
        dps = self.phases[min(self.phase, len(self.phases) - 1)]["dps"]
        for m in self.mechs:
            if not m.alive:
                continue
            self._move(m)
            self._weapons(m)
            if math.hypot(m.pos[0] - cx, m.pos[1] - cy) > cr:
                self._damage(m, dps * DT, None, "zone", None)
                m.last_combat = self.t
            elif self.t - m.last_combat > m.stats["regen_delay"] and m.hp < m.max_hp:
                m.hp = min(m.max_hp, m.hp + m.stats["regen_per_s"] * DT)
        self._projectiles()
        self._npcs()
        self._collect()

    def _move(self, m: Mech):
        s, c = m.stats, m.cmd
        ay = c.get("aim") or m.aim
        tr, pr = s["turn_rate"] * DT, s["pitch_rate"] * DT
        dy = wrap(ay[0] - m.aim[0])
        m.aim[0] = wrap(m.aim[0] + max(-tr, min(tr, dy)))
        tp = max(s["min_pitch"], min(s["max_pitch"], ay[1] if len(ay) > 1 else 0.0))
        m.aim[1] += max(-pr, min(pr, tp - m.aim[1]))
        mv = c.get("move") or [0.0, 0.0]
        n = math.hypot(mv[0], mv[1])
        if n > 1:
            mv = [mv[0] / n, mv[1] / n]
            n = 1.0
        charging = any(w and w["kind"] == "laser" and w.get("charge", 0) > 0 for w in m.slots)
        boosting = bool(c.get("boost")) and m.energy > 0.5
        m.boosting = boosting and n > 0.1
        speed = s["boost_speed"] if (boosting and m.grounded and n > 0.1) else s["walk_speed"]
        if charging:
            speed *= s["charge_move_mult"]
        acc = (s["ground_accel"] if m.grounded else s["air_accel"]) * DT
        for i in (0, 1):
            dv = mv[i] * speed - m.vel[i]
            m.vel[i] += max(-acc, min(acc, dv))
        spent = False
        if boosting and m.grounded and n > 0.1:
            m.energy -= s["boost_drain"] * DT
            spent = True
        if c.get("jump") and m.grounded:
            m.vel[2] = s["jump_speed"]
            m.grounded = False
            c["jump"] = False
        if not m.grounded and boosting:
            m.vel[2] = min(m.vel[2] + s["jet_accel"] * DT, s["max_rise_speed"])
            m.energy -= s["jet_drain"] * DT
            spent = True
            if self.tick % 6 == 0:
                self._sound(m.pos, "jet", m.id)
        if spent:
            m.last_spend = self.t
        elif self.t - m.last_spend > s["energy_regen_delay"]:
            m.energy = min(s["energy"], m.energy + s["energy_regen"] * DT)
        m.energy = max(m.energy, 0.0)
        m.vel[2] -= s["gravity"] * DT
        # horizontal motion with wall sliding (axis by axis)
        for i in (0, 1):
            nx = list(m.pos)
            nx[i] += m.vel[i] * DT
            if self.passable(nx[0], nx[1], m.pos[2], s["step_up"]) and \
                    self.wm.minx < nx[0] < self.wm.maxx and self.wm.miny < nx[1] < self.wm.maxy:
                m.pos[i] = nx[i]
            else:
                m.vel[i] = 0.0
        m.pos[2] += m.vel[2] * DT
        sup = self.support(m.pos[0], m.pos[1], m.pos[2])
        if m.pos[2] <= sup:
            if sup - m.pos[2] <= s["step_up"] + 0.6 or m.grounded:
                m.pos[2] = sup
            m.vel[2] = max(m.vel[2], 0.0)
            m.grounded = True
        else:
            m.grounded = m.pos[2] - sup < 0.05
        hs = math.hypot(m.vel[0], m.vel[1])
        if m.grounded and hs > self.rules["sound"]["step_speed"]:
            m.step_t += DT
            if m.step_t >= self.rules["sound"]["step_every"]:
                m.step_t = 0.0
                self._sound(m.pos, "boost" if speed > s["walk_speed"] else "step", m.id)

    # ------------------------------------------------------------------ weapons
    def _muzzle(self, m: Mech):
        a = m.aim
        d = [math.cos(a[1]) * math.cos(a[0]), math.cos(a[1]) * math.sin(a[0]), math.sin(a[1])]
        off = m.radius + 0.5
        return [m.pos[0] + d[0] * off, m.pos[1] + d[1] * off, m.pos[2] + m.stats["muzzle_height"] * m.size + d[2] * off], d

    def _weapons(self, m: Mech):
        fire = m.cmd.get("fire") or [False, False]
        for i, w in enumerate(m.slots):
            if w is None:
                continue
            w["cooldown"] = max(w["cooldown"] - DT, 0.0)
            ws = m.wstats[w["kind"]]
            if w["kind"] == "gun":
                if w["reload"] > 0:
                    w["reload"] -= DT
                    if w["reload"] <= 0:
                        w["ammo"] = int(ws["mag"])
                        w["reload"] = 0.0
                if i < len(fire) and fire[i] and w["cooldown"] <= 0 and w["ammo"] > 0 and w["reload"] <= 0:
                    p, d = self._muzzle(m)
                    sp = math.radians(ws["spread_deg"])
                    yaw = math.atan2(d[1], d[0]) + self.rng.gauss(0, sp)
                    pit = math.asin(max(-1, min(1, d[2]))) + self.rng.gauss(0, sp)
                    v = [math.cos(pit) * math.cos(yaw) * ws["speed"], math.cos(pit) * math.sin(yaw) * ws["speed"],
                         math.sin(pit) * ws["speed"]]
                    self.bullets.append({"id": self._nid("proj"), "kind": "gun", "pos": p, "vel": v, "owner": m.id,
                                         "dmg": ws["damage"] * m.dmg_mult(self.rules), "ttl": ws["range"] / ws["speed"],
                                         "weapon": "gun", "r": self.rules["projectile"]["gun_radius"],
                                         "cls": self._shot_cls(m, "gun")})
                    m.shots["gun"] = m.shots.get("gun", 0) + 1
                    others = [math.hypot(o.pos[0] - m.pos[0], o.pos[1] - m.pos[1]) for o in self.mechs
                              if o.alive and o is not m and not (o.house and m.house)]
                    if others:
                        m.shot_d.append(min(others))
                    w["ammo"] -= 1
                    w["cooldown"] = ws["cooldown"]
                    if w["ammo"] <= 0:
                        w["reload"] = ws["reload"]
                    self._sound(m.pos, "gun", m.id)
                    m.last_combat = self.t
            elif w["kind"] == "laser":
                held = i < len(fire) and fire[i]
                if held and w["cooldown"] <= 0:
                    if w.get("charge", 0) == 0 and self.tick % 4 == 0:
                        self._sound(m.pos, "laser_charge", m.id)
                    w["charge"] = w.get("charge", 0.0) + DT
                    if w["charge"] >= ws["charge"] + ws["hold_s"]:
                        self._laser(m, w, ws)
                elif w.get("charge", 0) > 0:
                    if w["charge"] >= ws["min_charge"]:
                        self._laser(m, w, ws)
                    elif not held:
                        w["charge"] += DT
            elif w["kind"] == "lightning":
                if i < len(fire) and fire[i] and w["cooldown"] <= 0 and m.energy >= ws["energy"]:
                    self._lightning(m, w, ws)
            elif w["kind"] == "mortar":
                if i < len(fire) and fire[i] and w["cooldown"] <= 0:
                    p, d = self._muzzle(m)
                    p[2] = m.pos[2] + m.height + 0.5
                    v = [d[0] * ws["speed"], d[1] * ws["speed"], d[2] * ws["speed"]]
                    self.shells.append({"id": self._nid("proj"), "kind": "mortar", "pos": p, "vel": v, "owner": m.id,
                                        "dmg": ws["damage"] * m.dmg_mult(self.rules), "ttl": ws["ttl"], "weapon": "mortar"})
                    m.shots["mortar"] = m.shots.get("mortar", 0) + 1
                    w["cooldown"] = ws["cooldown"]
                    self._sound(m.pos, "mortar", m.id)
                    m.last_combat = self.t

    def _targets(self):
        for o in self.mechs:
            if o.alive:
                yield ("mech", o, o.pos, o.radius, o.height)
        for n in self.npcs:
            if n["hp"] > 0:
                yield ("npc", n, n["pos"], 1.8, 3.5)
        for c in self.crates:
            yield ("crate", c, c["pos"], 1.4, 2.4)

    def _ray(self, m: Mech, p, d, rng):
        """First target hit by a ray from p along d within rng (walls stop it). Returns (kind, obj, dist)."""
        best = None
        for kind, obj, tp, rad, h in self._targets():
            if obj is m:
                continue
            cx, cy = tp[0] - p[0], tp[1] - p[1]
            hd = math.hypot(d[0], d[1]) or 1e-9
            s = (cx * d[0] + cy * d[1]) / (hd * hd)
            if s <= 0:
                continue
            qx, qy = p[0] + d[0] * s, p[1] + d[1] * s
            if math.hypot(qx - tp[0], qy - tp[1]) > rad:
                continue
            z = p[2] + d[2] * s
            if not (tp[2] - 0.2 <= z <= tp[2] + h + 0.2):
                continue
            dist = s * math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
            if dist <= rng and (best is None or dist < best[2]):
                best = (kind, obj, dist)
        if best is not None:
            end = [p[0] + d[0] * best[2], p[1] + d[1] * best[2], p[2] + d[2] * best[2]]
            if not self.los(p, end):
                return None
        return best

    def _shot_cls(self, m: Mech, weapon: str) -> Optional[str]:
        """Telemetry: weapon, range bin and motion of the nearest enemy mech at the moment m fires."""
        best = None
        for o in self.mechs:
            if o.alive and o is not m and not (o.house and m.house):
                d = math.hypot(o.pos[0] - m.pos[0], o.pos[1] - m.pos[1])
                if best is None or d < best[0]:
                    best = (d, o)
        if best is None:
            return None
        d, o = best
        sp = math.hypot(o.vel[0], o.vel[1])
        if not o.grounded:
            mot = "jumping"
        elif o.boosting:
            mot = "boosting"
        elif sp < 1.5:
            mot = "still"
        else:
            ux, uy = (o.pos[0] - m.pos[0]) / max(d, 1e-6), (o.pos[1] - m.pos[1]) / max(d, 1e-6)
            mot = "strafing" if abs(o.vel[0] * uy - o.vel[1] * ux) > 0.6 * sp else "radial"
        rb = "0-50" if d < 50 else "50-100" if d < 100 else "100-150" if d < 150 else "150+"
        k = f"{weapon}|{rb}|{mot}"
        m.shot_cls[k] = m.shot_cls.get(k, 0) + 1
        return k

    def _laser(self, m: Mech, w, ws):
        m.shots["laser"] = m.shots.get("laser", 0) + 1
        cls = self._shot_cls(m, "laser")
        frac = min(w["charge"], ws["charge"]) / ws["charge"]
        dmg = ws["damage"] * (ws["min_frac"] + (1 - ws["min_frac"]) * frac) * m.dmg_mult(self.rules)
        p, d = self._muzzle(m)
        hit = self._ray(m, p, d, ws["range"])
        end = [p[0] + d[0] * ws["range"], p[1] + d[1] * ws["range"], p[2] + d[2] * ws["range"]]
        if hit is not None:
            end = [p[0] + d[0] * hit[2], p[1] + d[1] * hit[2], p[2] + d[2] * hit[2]]
            self._hit(m, hit[0], hit[1], dmg, "laser", p)
            if hit[0] == "mech" and cls:
                m.hit_cls[cls] = m.hit_cls.get(cls, 0) + 1
        for o in self.mechs:
            if o.alive and o is not m and (self._sees(o, p, 0.1) or self._sees(o, end, 0.1)):
                o.beams.append({"by": m.id, "kind": "laser", "path": [p, end], "age": 0.0})
        w["charge"] = 0.0
        w["cooldown"] = ws["cooldown"]
        self._sound(m.pos, "laser", m.id)
        m.last_combat = self.t

    def _lightning(self, m: Mech, w, ws):
        m.shots["lightning"] = m.shots.get("lightning", 0) + 1
        m.energy -= ws["energy"]
        m.last_spend = self.t
        w["cooldown"] = ws["cooldown"]
        self._sound(m.pos, "lightning", m.id)
        eye = [m.pos[0], m.pos[1], m.pos[2] + m.stats["muzzle_height"] * m.size]
        cands = []
        for kind, obj, tp, rad, h in self._targets():
            if obj is m:
                continue
            dd = math.hypot(tp[0] - eye[0], tp[1] - eye[1])
            if dd > ws["range"]:
                continue
            if abs(wrap(math.atan2(tp[1] - eye[1], tp[0] - eye[0]) - m.aim[0])) > math.radians(ws["cone_deg"]) / 2:
                continue
            if self.los(eye, [tp[0], tp[1], tp[2] + h / 2]):
                cands.append((dd, kind, obj, tp))
        if not cands:
            return
        cands.sort(key=lambda c: c[0])
        _, kind, obj, tp = cands[0]
        dmg = ws["damage"] * m.dmg_mult(self.rules)
        path = [eye, [tp[0], tp[1], tp[2] + 2]]
        self._hit(m, kind, obj, dmg, "lightning", eye)
        done = {id(obj)}
        last = tp
        for _ in range(int(ws["chain"])):
            dmg *= ws["chain_falloff"]
            nxt = None
            for k2, o2, p2, _, _ in self._targets():
                if id(o2) in done or o2 is m:
                    continue
                if math.hypot(p2[0] - last[0], p2[1] - last[1]) <= ws["chain_range"]:
                    nxt = (k2, o2, p2)
                    break
            if nxt is None:
                break
            done.add(id(nxt[1]))
            self._hit(m, nxt[0], nxt[1], dmg, "lightning", last)
            path.append([nxt[2][0], nxt[2][1], nxt[2][2] + 2])
            last = nxt[2]
        for o in self.mechs:
            if o.alive and o is not m and math.hypot(o.pos[0] - eye[0], o.pos[1] - eye[1]) < 200:
                o.beams.append({"by": m.id, "kind": "lightning", "path": path, "age": 0.0})
        m.last_combat = self.t

    def _projectiles(self):
        keep = []
        for b in self.bullets:
            p0 = b["pos"]
            p1 = [p0[0] + b["vel"][0] * DT, p0[1] + b["vel"][1] * DT, p0[2] + b["vel"][2] * DT]
            b["ttl"] -= DT
            owner = self.mechs[b["owner"]] if b["owner"] < 100 else None
            d = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]]
            hit = None
            for kind, obj, tp, rad, h in self._targets():
                if obj is owner or (b["owner"] >= 100 and kind == "npc"):
                    continue
                if owner is not None and owner.house and kind == "mech" and obj.house:
                    continue                                   # the squad never fights itself
                cx, cy = tp[0] - p0[0], tp[1] - p0[1]
                hd2 = d[0] ** 2 + d[1] ** 2 or 1e-9
                s = max(0.0, min(1.0, (cx * d[0] + cy * d[1]) / hd2))
                qx, qy = p0[0] + d[0] * s, p0[1] + d[1] * s
                if math.hypot(qx - tp[0], qy - tp[1]) <= rad + b["r"]:
                    z = p0[2] + d[2] * s
                    if tp[2] - 0.2 <= z <= tp[2] + h + 0.2 and (hit is None or s < hit[2]):
                        hit = (kind, obj, s)
            if hit is not None and self.los(p0, [p0[0] + d[0] * hit[2], p0[1] + d[1] * hit[2], p0[2] + d[2] * hit[2]]):
                if b["owner"] < 100:
                    self._hit(owner, hit[0], hit[1], b["dmg"], b["weapon"], p0)
                    if hit[0] == "mech" and b.get("cls"):
                        owner.hit_cls[b["cls"]] = owner.hit_cls.get(b["cls"], 0) + 1
                elif hit[0] == "mech":
                    self._damage(hit[1], b["dmg"], None, "npc", p0, npc_id=b["owner"])
                continue
            k = self.wm.idx(p1[0], p1[1])
            if b["ttl"] <= 0 or self.wm.roof[k] > p1[2] or self.wm.gnd[k] > p1[2]:
                continue
            b["pos"] = p1
            keep.append(b)
        self.bullets = keep
        keep = []
        mr = self.rules["weapons"]["mortar"]
        for s in self.shells:
            s["vel"][2] -= mr["gravity"] * DT
            p = [s["pos"][i] + s["vel"][i] * DT for i in range(3)]
            s["ttl"] -= DT
            k = self.wm.idx(p[0], p[1])
            boom = s["ttl"] <= 0 or self.wm.roof[k] > p[2] or self.wm.gnd[k] > p[2]
            direct = None
            for o in self.mechs:
                if o.alive and o.id != s["owner"] and math.hypot(o.pos[0] - p[0], o.pos[1] - p[1]) < o.radius \
                        and o.pos[2] <= p[2] <= o.pos[2] + o.height:
                    direct, boom = o, True
            if boom:
                self._explode(s, p, direct)
                continue
            s["pos"] = p
            keep.append(s)
        self.shells = keep

    def _explode(self, s, p, direct):
        mr = self.rules["weapons"]["mortar"]
        owner = self.mechs[s["owner"]]
        self._sound(p, "explosion", -1)
        mult = owner.dmg_mult(self.rules)
        if direct is not None:
            self._hit(owner, "mech", direct, s["dmg"], "mortar", p)
        for kind, obj, tp, rad, h in list(self._targets()):
            d = math.hypot(tp[0] - p[0], tp[1] - p[1])
            if d > mr["splash_radius"] or obj is direct:
                continue
            f = 1 - (1 - mr["splash_edge"]) * d / mr["splash_radius"]
            dmg = mr["splash"] * f * mult * (owner.stats["self_damage_mult"] if obj is owner else 1)
            if obj is owner:
                self._damage(owner, dmg, owner, "mortar", p)
            else:
                self._hit(owner, kind, obj, dmg, "mortar", p)

    def _hit(self, att: Mech, kind, obj, dmg, weapon, origin):
        if kind == "mech" and att is not None and att.house and obj.house:
            return                                             # the squad never fights itself
        if kind == "npc" and att is not None and not att.house and obj["hp"] - dmg <= 0:
            self.telemetry["drone_kills"] += 1
        if kind == "mech":
            if att is not None:
                obj.first_hit.setdefault(att.id, self.t)
            done = self._damage(obj, dmg, att, weapon, origin)
            att.hits[weapon] = att.hits.get(weapon, 0) + 1
            if weapon == "gun":
                att.hit_d.append(math.hypot(obj.pos[0] - att.pos[0], obj.pos[1] - att.pos[1]))
            att.dmg_dealt += done
            att.events.append({"type": "hit", "target": obj.id, "amount": round(done, 1), "weapon": weapon})
            att.last_combat = self.t
        elif kind == "npc":
            obj["hp"] -= dmg
            obj["target"], obj["target_t"] = att.id, self.t
            att.events.append({"type": "hit", "target": obj["id"], "amount": round(dmg, 1), "weapon": weapon})
            if obj["hp"] <= 0:
                for _ in range(int(self.rules["npc"]["cubes"])):
                    self._cube(obj["pos"])
        elif kind == "crate":
            obj["hp"] -= dmg
            att.events.append({"type": "hit", "target": obj["id"], "amount": round(dmg, 1), "weapon": weapon})
            if obj["hp"] <= 0 and obj in self.crates:
                self.crates.remove(obj)
                self._sound(obj["pos"], "crate", -1)
                self._cube(obj["pos"])
                if self.rng.random() < self.rules["loot"]["crate_weapon_chance"]:
                    kinds = [k for k, w in self.rules["loot"]["weights"].items() for _ in range(int(w))]
                    self._drop_pickup(self.rng.choice(kinds), obj["pos"])

    def _damage(self, m: Mech, dmg, att: Optional[Mech], weapon, origin, npc_id=None) -> float:
        if not m.alive:
            return 0.0
        rear = False
        bearing = None
        if origin is not None:
            bearing = math.atan2(origin[1] - m.pos[1], origin[0] - m.pos[0])
            if weapon != "zone":
                rear = abs(wrap(bearing - m.aim[0])) > math.radians(m.stats["front_arc_deg"]) / 2
                if rear:
                    dmg *= m.stats["rear_mult"]
                    m.rear_hits = getattr(m, "rear_hits", 0) + 1
                dmg *= max(0.0, 1 - m.stats.get("armor", 0.0))
        m.hp -= dmg
        m.dmg_taken += dmg
        m.last_combat = self.t
        by = att.id if att is not None else npc_id
        src = att.pos if att is not None else origin
        m.dmg_log.append((self.t, by, weapon, dmg, None if src is None else math.hypot(src[0] - m.pos[0], src[1] - m.pos[1])))
        if att is not None and not att.house and m.house:
            m.min_hp_by_entrant = min(m.min_hp_by_entrant, max(m.hp, 0) / m.max_hp)
            m.entrant_last_hit = self.t
        ev = {"type": "damaged", "amount": round(dmg, 1), "weapon": weapon,
              "bearing": None if bearing is None else round(bearing, 3), "by": by}
        if rear:
            ev["rear"] = True
        m.events.append(ev)
        if m.hp <= 0:
            m.death_t, m.death_cause = self.t, weapon
            m.death_by = ("entrant" if not att.house else "house") if att is not None else \
                ("zone" if weapon == "zone" else ("drone" if weapon == "npc" else weapon))
            m.death_dist = None if src is None else math.hypot(src[0] - m.pos[0], src[1] - m.pos[1])
            ctrl_plan = getattr(m.ctrl, "last_plan", None)
            m.death_mode = getattr(ctrl_plan, "mode", None)
            m.death_rationale = getattr(ctrl_plan, "rationale", None)
            k = self.wm.idx(m.pos[0], m.pos[1])
            m.death_where = "roof" if self.wm.elevated(m.pos[0], m.pos[1], m.pos[2]) else (
                "cover" if self.wm.cover[k] >= 3 else "open")
            m.death_engagers = len({b for (tt, b, w, a, dd) in m.dmg_log if self.t - tt <= 5.0 and b is not None and b < 100})
            m.death_weapons = [w["kind"] for w in m.slots if w]
            m.house_dead_at_death = sum(1 for o in self.mechs if o.house and not o.alive)
            m.hp_15s_before = next((h for (tt, h, e) in m.hp_hist if self.t - tt <= 15.0), None)
            self._die(m, att)
        return dmg

    def _die(self, m: Mech, killer: Optional[Mech]):
        m.alive = False
        m.hp = 0.0
        # same-tick deaths share the placement of the first one this tick (= mechs alive before the tick)
        if getattr(self, "_place_tick", None) != self.tick:
            self._place_tick, self._place_base = self.tick, sum(1 for o in self.mechs if o.alive) + 1
        m.place = self._place_base
        if killer is not None and killer is not m:
            killer.kills += 1
            if killer.id in m.first_hit:
                killer.ttk.append(self.t - m.first_hit[killer.id])
            killer.events.append({"type": "kill", "target": m.id})
        for w in m.slots:
            if w and w["kind"] != "gun":
                self._drop_pickup(w["kind"], m.pos, w)
        for _ in range(m.cubes + int(self.rules["cubes"]["death_drop_extra"])):
            self._cube(m.pos)
        self._sound(m.pos, "death", m.id)
        try:
            if hasattr(m.ctrl, "end"):
                m.ctrl.end(m.place)
        except Exception:
            pass

    def _cube(self, p):
        a, d = self.rng.uniform(-math.pi, math.pi), self.rng.uniform(0, 3)
        x, y = p[0] + math.cos(a) * d, p[1] + math.sin(a) * d
        self.cubes.append({"id": self._nid("cube"), "pos": [x, y, self.support(x, y, p[2] + 1)]})

    def _collect(self):
        if self.tick % 2:
            return
        rad = self.rules["cubes"]["pickup_radius"]
        for c in list(self.cubes):
            best, bd = None, rad
            for m in self.mechs:
                if m.alive:
                    d = math.hypot(m.pos[0] - c["pos"][0], m.pos[1] - c["pos"][1])
                    if d <= bd and abs(m.pos[2] - c["pos"][2]) < 4:
                        best, bd = m, d
            if best is not None:
                self.cubes.remove(c)
                best.cubes += 1
                if best.cubes <= self.rules["cubes"]["stat_cap"]:
                    gain = self.rules["mech"]["hp"] * self.rules["cubes"]["hp_per_cube"]
                    best.max_hp += gain
                    best.hp += gain
                best.events.append({"type": "pickup", "cubes": best.cubes})
                best.cube_t = getattr(best, "cube_t", []) + [self.t]
                self._maybe_offer(best)

    def _npcs(self):
        r = self.rules["npc"]
        for n in self.npcs:
            if n["hp"] <= 0:
                continue
            n["cool"] -= DT
            if n["cool"] > 0:
                continue
            tgt = None
            if n["target"] is not None and self.t - n["target_t"] < 10:
                o = self.mechs[n["target"]]
                if o.alive and math.hypot(o.pos[0] - n["pos"][0], o.pos[1] - n["pos"][1]) < r["deaggro_range"]:
                    tgt = o
            if tgt is None:
                best = None
                for o in self.mechs:
                    if not o.alive:
                        continue
                    d = math.hypot(o.pos[0] - n["pos"][0], o.pos[1] - n["pos"][1])
                    if d < r["aggro_range"] and (best is None or d < best[0]):
                        best = (d, o)
                tgt = best[1] if best else None
            if tgt is None:
                continue
            src = [n["pos"][0], n["pos"][1], n["pos"][2] + 2.5]
            dst = [tgt.pos[0], tgt.pos[1], tgt.pos[2] + tgt.height / 2]
            if not self.los(src, dst):
                continue
            d = math.dist(src, dst)
            yaw = math.atan2(dst[1] - src[1], dst[0] - src[0]) + self.rng.gauss(0, math.radians(r["spread_deg"]))
            pit = math.atan2(dst[2] - src[2], math.hypot(dst[0] - src[0], dst[1] - src[1]))
            sp = r["projectile_speed"]
            self.bullets.append({"id": self._nid("proj"), "kind": "npc", "pos": src, "owner": n["id"],
                                 "vel": [math.cos(pit) * math.cos(yaw) * sp, math.cos(pit) * math.sin(yaw) * sp, math.sin(pit) * sp],
                                 "dmg": r["damage"], "ttl": d / sp + 0.5, "weapon": "npc", "r": 0.3})
            n["cool"] = r["cooldown"]
            self._sound(src, "npc_gun", -1)
