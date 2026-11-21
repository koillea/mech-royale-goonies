"""MechBot: plan(obs) -> execute(plan) every decision.

Life cycle per decision (10 per match-second, 50 ms budget):
  ingest events into Memory -> HeuristicPlanner.plan() -> movement (A* path, strafe, dodge, unstick)
  -> aim and triggers per weapon -> upgrade pick and pickup take -> action dict.
"""
from __future__ import annotations

import gc
import math
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .aim import TargetTracker, rear_exposure
from .intel import Intel
from .ballistics import aim_at, lead, mortar_pitch, mortar_time, wrap, yaw_to
from .config import BotConfig
from .plan import HeuristicPlanner, Hold, Plan, dist2, zone_now
from .position import PositionPlanner, Spot
from .worldmap import PathSearch, WorldMap

LOUD = {"gun", "laser", "mortar", "explosion", "lightning", "laser_charge"}


def log(*a: Any) -> None:
    print(*a, file=sys.stderr, flush=True)


class Memory:
    """What happened to us: who hit us and from where, and what we heard."""

    def __init__(self) -> None:
        self.attackers: Dict[int, float] = {}       # id -> last time it hit us
        self.dmg_bearing: Optional[float] = None
        self.dmg_t = -1e9
        self.dmg_by: Optional[int] = None
        self.sounds: List[Tuple[float, float, str]] = []   # (t, bearing, dist)
        self.took_damage_t = -1e9
        self.mech_shot_t = -1e9

    def ingest(self, obs: Dict[str, Any]) -> None:
        t = obs["t"]
        for e in obs.get("events", []):
            if e.get("type") == "damaged":
                self.took_damage_t = t
                if e.get("by") is not None:
                    self.attackers[int(e["by"])] = t
                    self.dmg_by = int(e["by"])
                    if int(e["by"]) < 100:
                        self.mech_shot_t = t
                if e.get("bearing") is not None:
                    self.dmg_bearing, self.dmg_t = e["bearing"], t
        for s in obs.get("sounds", []):
            if s["kind"] in LOUD and s["dist"] in ("near", "mid"):
                self.sounds.append((t - s.get("age", 0), s["bearing"], s["dist"]))
        self.sounds = [s for s in self.sounds if t - s[0] < 3.0][-20:]

    def shot_recently(self, t: float, window: float) -> bool:
        return t - self.mech_shot_t < window

    def hostile_ids(self, t: float, window: float) -> set:
        return {k for k, v in self.attackers.items() if t - v < window}

    def recent_damage_bearing(self, t: float, window: float) -> Optional[float]:
        return self.dmg_bearing if t - self.dmg_t < window else None

    def loud_bearing(self, t: float) -> Optional[float]:
        near = [s for s in self.sounds if s[2] == "near" and t - s[0] < 1.5]
        if near:
            return near[-1][1]
        return None


class MechBot:
    def __init__(self, hello: Dict[str, Any], cfg: Optional[BotConfig] = None):
        t0 = time.time()
        self.cfg = cfg or BotConfig()
        self.name = self.cfg.name
        self.rules = hello.get("config", {})
        self.mech_rules = self.rules.get("mech", {})
        self.rng = random.Random(hello.get("seed", 0))
        self.planner = HeuristicPlanner(self.cfg, self.rules)
        self.mem = Memory()
        self.tracker: TargetTracker = TargetTracker(None, self.mech_rules.get("gravity", 22.0),
                                                    self.cfg.track_window_s, self.cfg.reversals_for_mean)
        self.wm: Optional[WorldMap] = None
        here = os.path.dirname(os.path.abspath(__file__))
        dirs = [hello.get("map", {}).get("dir"), "/arena", os.path.join(here, "..", "arena"), os.path.join(here, "..", "..", "arena")]
        for d in dirs:
            if d and os.path.exists(os.path.join(d, "v2", "world.json")):
                try:
                    self.wm = WorldMap(d, step_up=self.mech_rules.get("step_up", 1.2),
                                       head=self.mech_rules.get("height", 9.0),
                                       max_slope_deg=self.mech_rules.get("max_slope_deg", 50.0))
                    break
                except Exception as e:  # never die at hello: fall back to direct steering
                    log("map load failed", d, repr(e))
        self.pos_planner: Optional[PositionPlanner] = None
        if self.wm is not None:
            try:
                self.pos_planner = PositionPlanner(self.wm, self.cfg, self.rules)
            except Exception as e:
                log("position planner failed", repr(e))
        self.spot: Optional[Spot] = None
        self.spot_key: Optional[Tuple[float, float, float]] = None
        self.spot_t = -1e9
        self.bad_perch: Dict[int, float] = {}
        self.climb_t0: Optional[float] = None
        self.hold: Optional[Hold] = None
        self.path: Optional[List[Tuple[float, float]]] = None
        self.path_goal: Optional[Tuple[float, float]] = None
        self.path_i = 0
        self.search: Optional[PathSearch] = None
        self.search_goal: Optional[Tuple[float, float]] = None
        self.plan_t = -1e9
        self.slow_since: Optional[float] = None
        self.jet_until = -1e9
        self.detour_until = -1e9
        self.detour_yaw = 0.0
        self.stuck_hits: List[float] = []
        self.strafe_sign = 1.0
        self.strafe_until = 0.0
        self.hop_t = 0.0
        self.last_plan: Optional[Plan] = None
        self.cover: Optional[Tuple[float, float]] = None
        self.cover_peek: Optional[Tuple[float, float]] = None
        self.cover_t = -1e9
        self.cover_from: Optional[List[float]] = None
        self.cstate: Optional[str] = None            # TAKE_COVER | COVERED | PEEK
        self.covered_t0 = -1e9
        self.peek_t0 = -1e9
        self.relocations: List[float] = []
        self.tracker.wm = self.wm
        self.intel = Intel(self.cfg, self.rules)
        gc.collect()
        gc.freeze()   # the map's objects never die: keep the collector from rescanning them mid-match
        log(f"{self.name}: init {time.time() - t0:.2f}s map={'ok' if self.wm else 'none'} "
            f"perches={len(self.pos_planner.perches) if self.pos_planner else 0}")

    # ================================================================== decision
    def act(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        self._t0 = time.perf_counter()
        self.mem.ingest(obs)
        self.tracker.update(obs)
        self.intel.update(obs)
        self._update_spot(obs)
        self.hold = self._hold(obs)
        plan = self.planner.plan(obs, self.mem, self.hold)
        self._combat(obs, plan)
        self.last_plan = plan
        act: Dict[str, Any] = {"tick": obs["tick"]}
        move, boost, jump = self._move(obs, plan)
        aim, fire, reload_ = self._aim_fire(obs, plan, move)
        act.update(move=[round(move[0], 3), round(move[1], 3)], boost=boost, jump=jump,
                   aim=[round(aim[0], 4), round(aim[1], 4)], fire=fire)
        if reload_:
            act["reload"] = True
        self._offer(obs, act)
        self._take(obs, act)
        act["debug"] = {"label": plan.rationale[:80]}
        return act

    # ================================================================== position
    def _update_spot(self, obs) -> None:
        if self.pos_planner is None:
            return
        z, t = obs["zone"], obs["t"]
        key = (round(z["next_center"][0], 1), round(z["next_center"][1], 1), round(z["next_radius"], 1))
        new_ring = key != self.spot_key
        if new_ring or self.spot is None or (t - self.spot_t > self.cfg.respot_s and self.climb_t0 is None):
            heard = [(th.pos[0], th.pos[1], th.conf_at(t, self.cfg.intel_half_life_s))
                     for th in self.intel.active(t, obs["self"]["pos"], 0.3) if th.src not in ("seen",)]
            self.spot = self.pos_planner.choose(obs, None if new_ring else self.spot, self.bad_perch, heard)
            self.spot_key, self.spot_t = key, t
            self.climb_t0 = None if new_ring else self.climb_t0
            self.path = None if new_ring else self.path

    def _elevated(self, me) -> bool:
        p = me["pos"]
        return self.wm is not None and self.wm.elevated(p[0], p[1], p[2])

    def _hold(self, obs) -> Optional[Hold]:
        sp = self.spot
        if sp is None:
            return None
        me, t = obs["self"], obs["t"]
        pos = me["pos"]
        d = dist2(pos, (sp.x, sp.y))
        if sp.kind == "ground":
            self.climb_t0 = None
            return Hold(goal=(sp.x, sp.y) if d > 2.5 else None, spot=(sp.x, sp.y), why=sp.why)
        p = sp.perch
        on_perch = self._elevated(me) and abs(pos[2] - sp.z) < 1.5
        if on_perch:
            self.climb_t0 = None
            return Hold(goal=(sp.x, sp.y) if d > 2.0 else None, spot=(sp.x, sp.y), perched=True, why=sp.why)
        if self.climb_t0 is not None and t - self.climb_t0 > self.cfg.climb_timeout_s:
            self.bad_perch[p.pid] = t + self.cfg.bad_perch_s          # could not get up: try elsewhere
            self.climb_t0, self.spot_t = None, -1e9
            self._update_spot(obs)
            return self._hold(obs) if self.spot is not None and self.spot is not sp else None
        lx, ly = self.pos_planner.launch_for(p, pos)
        if self.climb_t0 is None and dist2(pos, (lx, ly)) > 3.5:
            return Hold(goal=(lx, ly), spot=(sp.x, sp.y), why=f"to wall of {sp.why}")
        return Hold(goal=None, spot=(sp.x, sp.y), climbing=True, why=f"up {sp.why}")

    def _climb(self, obs, mx: float, my: float, boost: bool, jump: bool):
        """At the wall: wait for enough energy, then jump and jet into the wall until the feet clear the roof edge
        (protocol section 7 Movement: taller ledges are walls until your feet are above them)."""
        me, t, sp = obs["self"], obs["t"], self.spot
        pos = me["pos"]
        p = sp.perch
        st = me["stats"]
        per_energy = st.get("max_rise_speed", 10.0) / max(st.get("jet_drain", 15.0), 1e-6)
        need = max(p.top - pos[2], 0.0) / per_energy + self.cfg.climb_energy_margin
        if self.climb_t0 is None:
            if me["energy"] < min(need, me["max_energy"] * 0.98):
                return mx * 0.3, my * 0.3, False, False          # wait at the wall (keep any evasive drift small)
            self.climb_t0 = t
        rx, ry = self.pos_planner.nearest_roof_cell(p, pos)
        if pos[2] > p.top + 0.4:
            rx, ry = sp.x, sp.y                                   # above the edge: step in over the roof
        d = math.hypot(rx - pos[0], ry - pos[1])
        mx, my = ((rx - pos[0]) / d, (ry - pos[1]) / d) if d > 1e-6 else (0.0, 0.0)
        if me.get("grounded", True):
            jump = pos[2] < p.top - 0.5
            boost = False
        else:
            boost = pos[2] < p.top + 1.0 and me["energy"] > 1
        return mx, my, boost, jump

    # ================================================================== cover
    def _combat(self, obs, plan: Plan) -> None:
        """Get behind cover when shot, then fire back from the best angle.

        Starts when a mech damages us (or v3's bad-fight rule: it has a laser we lack, or we are losing on HP):
          TAKE_COVER  run to the nearest point hidden from the shooter AND, as far as intel knows, from the other
                      mechs around (footsteps, jets, gunfire, beams, bullets), preferring points that have a peek
                      spot toward the shooter, on its back side and higher up; firing on the way if clear
          COVERED     reload, let the laser cool, regenerate, pre-aim at where the shooter will appear
          PEEK        step to the chosen firing spot, shoot, duck back when hit, dry, laser fired, or peek_max_s
        It never flees from a pusher: a shooter inside brawl_range, or one that walks around our cover and sees
        us there, gets fought in the open (strafing). The zone always comes first (ROTATE is planned before this).
        """
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        if self.wm is None or not cfg.intel_cover or plan.mode not in ("FIGHT", "ALERT"):
            self.cstate = None
            return
        pos = me["pos"]
        shot = self.mem.shot_recently(t, cfg.shot_window_s)
        # primary threat: the planned target if it is a mech, else the most dangerous hostile intel estimate
        if plan.target is not None and plan.target_kind == "mech":
            primary, pid = list(plan.target["pos"]), plan.target["id"]
        else:
            hostile = [th for th in self.intel.active(t, pos) if t - th.hostile_t < cfg.cover_cycle_s]
            if not hostile:
                self.cstate = None
                return
            primary, pid = list(hostile[0].pos), hostile[0].mech_id
        tgt = plan.target if plan.target_kind == "mech" else None
        laser_gap = tgt is not None and "laser" in tgt.get("weapons", []) \
            and not any(w and w["kind"] == "laser" for w in me["weapons"])
        losing = tgt is not None and me["hp"] < tgt.get("hp", 1400) * 0.8
        in_cycle = self.cstate is not None and t - self.mem.mech_shot_t < cfg.cover_cycle_s
        if not (shot or in_cycle or laser_gap or losing or plan.retreat):
            self.cstate = None
            return
        d = dist2(pos, primary)
        if d < cfg.brawl_range:
            self.cstate = None                       # a pusher: fight it, do not turn our back
            return
        eye = [primary[0], primary[1], primary[2] + self.mech_rules.get("eye_height", 8.0)]
        top = 9.0 * (1 + 0.05 * me.get("cubes", 0))
        exposed = self.wm.los(eye, [pos[0], pos[1], pos[2] + top - 0.3])
        at_cover = self.cover is not None and dist2(pos, self.cover) < 1.0
        if self.cstate == "COVERED" and exposed and d < cfg.flanked_fight_range:
            self.cstate = None                       # it walked around our cover: shoot back instead of fleeing
            return
        self.relocations = [r for r in self.relocations if t - r < cfg.cover_cycle_s]
        if (self.cover is None or self.cover_from is None or dist2(self.cover_from, primary) > 12.0
                or (at_cover and exposed) or (not at_cover and t - self.cover_t > 1.5)):
            if len(self.relocations) >= cfg.max_relocations:
                self.cstate = None                   # keeps getting found: stand and fight
                return
            others = [th for th in self.intel.active(t, pos) if th.mech_id != pid and
                      dist2(th.pos, primary) > 15.0]
            self.cover, self.cover_peek = self._find_cover(me, eye, primary, tgt, others, obs)
            self.cover_t, self.cover_from = t, primary
            if self.cover is not None:
                self.relocations.append(t)
            at_cover = self.cover is not None and dist2(pos, self.cover) < 1.0
        if self.cover is None:
            self.cstate = None
            return

        hp_frac = me["hp"] / max(me["max_hp"], 1.0)
        ws = [w for w in me["weapons"] if w]
        gun = next((w for w in ws if w["kind"] == "gun"), None)
        laser = next((w for w in ws if w["kind"] == "laser"), None)
        gun_ready = gun is not None and gun.get("reload", 0) == 0 and gun.get("ammo", 0) >= gun["stats"].get("mag", 12) * 0.5
        laser_ready = laser is not None and laser.get("cooldown", 0) <= 0.05
        gun_dry = gun is None or gun.get("ammo", 0) == 0 or gun.get("reload", 0) > 0
        if self.cstate == "PEEK":
            if ((shot and self.mem.mech_shot_t > self.peek_t0 + 0.2) or (gun_dry and not laser_ready)
                    or t - self.peek_t0 > cfg.peek_max_s or hp_frac < cfg.peek_min_hp or tgt is None):
                self.cstate = "TAKE_COVER"
        if self.cstate != "PEEK":
            prev = self.cstate
            self.cstate = "COVERED" if (at_cover and not exposed) else "TAKE_COVER"
            if self.cstate == "COVERED" and prev != "COVERED":
                self.covered_t0 = t
        if (self.cstate == "COVERED" and tgt is not None and self.cover_peek is not None
                and (gun_ready or laser_ready) and hp_frac >= cfg.peek_min_hp
                and t - self.covered_t0 >= cfg.min_cover_s):
            self.cstate, self.peek_t0 = "PEEK", t

        label = f"{pid if pid is not None else '?'} {d:.0f}m"
        if self.cstate == "TAKE_COVER":
            plan.mode, plan.goal, plan.boost = "COVER", self.cover, True
            plan.rationale = f"COVER from {label}" + (" shot" if shot else "")
        elif self.cstate == "COVERED":
            plan.mode, plan.goal, plan.boost = "COVERED", None, False
            plan.face_bearing = yaw_to(pos, primary)
            plan.rationale = f"COVERED from {label} hp {hp_frac:.0%}"
        else:
            plan.mode, plan.goal, plan.boost = "PEEK", self.cover_peek, False
            plan.rationale = f"PEEK at {label}"
        plan.retreat = False

    def _in_zone(self, obs, x: float, y: float, margin: float = 5.0) -> bool:
        (cx, cy), cr = zone_now(obs["zone"], obs["t"])
        return math.hypot(x - cx, y - cy) < cr - margin

    def _find_cover(self, me, eye, primary, tgt, others, obs):
        """Best nearby hiding spot and the firing spot that goes with it.

        A candidate must be walkable, inside the zone, reachable in a straight line, and hidden (centre and head)
        from the primary shooter. Cost = distance + penalty per other intel threat that can see it - bonus when a
        firing spot within peek_radius sees the shooter, more if that spot is on the shooter's back side
        (rear armour x1.5) or higher. Returns (cover, peek) or (None, None)."""
        cfg, wm, pos = self.cfg, self.wm, me["pos"]
        zr = pos[2] if self._elevated(me) else None
        mh = me["stats"].get("muzzle_height", 7.0)
        tc = [primary[0], primary[1], primary[2] + 4.5]
        away = yaw_to(eye, pos)
        best = (None, None, 1e18)
        for r in (4.0, 7.0, 10.0, 14.0, 19.0, 25.0, 32.0, 40.0):
            for k in range(16):
                a = away + (k - 8) * math.pi / 8
                x, y = pos[0] + math.cos(a) * r, pos[1] + math.sin(a) * r
                if not wm.walk_ok(x, y, zr) or not self._in_zone(obs, x, y):
                    continue
                g = zr if zr is not None else wm.ground(x, y)
                if wm.los(eye, [x, y, g + 9.0]) or wm.los(eye, [x, y, g + 4.5]):
                    continue
                cost = r + 0.3 * abs(wrap(a - away)) * r
                if cost >= best[2] or not self._line_ok(pos, (x, y), zr):
                    continue
                for th in others:
                    the = [th.pos[0], th.pos[1], th.pos[2] + 8.0]
                    if wm.los(the, [x, y, g + 9.0]):
                        cost += cfg.cover_other_penalty * th.conf
                peek, bonus = self._best_peek(me, (x, y), g, zr, tc, tgt, mh)
                cost -= bonus
                if cost < best[2]:
                    best = ((x, y), peek, cost)
            if best[0] is not None and r >= 10.0:
                break                                # nearest ring with a valid spot (plus one more) is enough
        return best[0], best[1]

    def _best_peek(self, me, cover, g, zr, tc, tgt, mh):
        """Firing spot near `cover` that sees the shooter: prefer its back side and higher ground."""
        cfg, wm = self.cfg, self.wm
        toward = yaw_to(cover, tc)
        best, bonus = None, 0.0
        for r in (3.0, 4.5, 6.0, 8.0):
            for k in range(10):
                a = toward + ((k + 1) // 2) * (1 if k % 2 else -1) * math.pi / 5
                x, y = cover[0] + math.cos(a) * r, cover[1] + math.sin(a) * r
                if not wm.walk_ok(x, y, zr):
                    continue
                gz = zr if zr is not None else wm.ground(x, y)
                if not wm.los([x, y, gz + mh], tc):
                    continue
                b = cfg.peek_bonus - r
                if tgt is not None and "aim" in tgt and rear_exposure(tgt, [x, y, gz]) > 0:
                    b += cfg.peek_rear_bonus
                b += min(max(gz - tc[2] + 4.5, 0.0), 10.0) * cfg.peek_height_bonus
                if b > bonus:
                    best, bonus = (x, y), b
            if best is not None:
                break
        return best, bonus

    def _line_ok(self, pos, b, zr) -> bool:
        if zr is None:
            return self.wm.line_walkable((pos[0], pos[1]), b)
        n = max(int(dist2(pos, b) / 1.5), 1)
        return all(self.wm.walk_ok(pos[0] + (b[0] - pos[0]) * s / n, pos[1] + (b[1] - pos[1]) * s / n, zr)
                   for s in range(1, n + 1))

    def _roof_z(self, me, goal) -> Optional[float]:
        """Our roof height if we are on a roof and mean to stay on it (no goal, or a goal on the same roof)."""
        if not self._elevated(me):
            return None
        z = me["pos"][2]
        if goal is None or self.wm.walk_ok(goal[0], goal[1], z):
            return z
        return None

    # ================================================================== movement
    def _move(self, obs, plan: Plan) -> Tuple[Tuple[float, float], bool, bool]:
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        boost, jump = plan.boost, False
        mx, my = 0.0, 0.0
        if plan.goal is not None:
            mx, my = self._steer(obs, plan.goal)

        tgt = plan.target if plan.target_kind in ("mech", "npc") else None
        mx, my, boost, jump = self._evade(obs, plan, mx, my, boost, jump)

        # dodge a laser that is charging at us (its aim is visible, section 7 Weapons)
        for m in obs["mechs"]:
            if m["kind"] == "mech" and m.get("charging"):
                to_me = yaw_to(m["pos"], pos)
                if abs(wrap(m["aim"][0] - to_me)) < 0.15 and dist2(m["pos"], pos) < 290:
                    side = 1.0 if wrap(m["aim"][0] - to_me) < 0 else -1.0
                    mx, my = math.cos(to_me + side * math.pi / 2), math.sin(to_me + side * math.pi / 2)
                    boost = True
                    break

        # keep out of drone aggro range unless we are fighting it
        for n in obs["mechs"]:
            if n["kind"] == "npc" and n is not tgt:
                d = dist2(n["pos"], pos)
                if d < cfg.npc_avoid:
                    w = (cfg.npc_avoid - d) / cfg.npc_avoid
                    mx += (pos[0] - n["pos"][0]) / max(d, 1) * w * 1.5
                    my += (pos[1] - n["pos"][1]) / max(d, 1) * w * 1.5

        # wall avoidance on the grid: if the cell a few metres ahead is solid (or, on a roof, off the edge),
        # rotate toward free space
        zr = self._roof_z(me, plan.goal) if self.wm is not None else None
        n = math.hypot(mx, my)
        if n > 1e-6:
            mx, my = mx / n, my / n
            leaving_roof = self._elevated(me) and zr is None
            if self.wm is not None and not leaving_roof and t > self.jet_until \
                    and not self.wm.walk_ok(pos[0] + mx * 4.0, pos[1] + my * 4.0, zr):
                base = math.atan2(my, mx)
                for da in (0.4, -0.4, 0.8, -0.8, 1.2, -1.2, 1.6, -1.6, 2.4, -2.4, math.pi):
                    a = base + da
                    if self.wm.walk_ok(pos[0] + math.cos(a) * 4.0, pos[1] + math.sin(a) * 4.0, zr):
                        mx, my = math.cos(a), math.sin(a)
                        break

        climbing = self.hold is not None and self.hold.climbing and plan.mode not in ("COVER", "COVERED", "PEEK", "ROTATE")
        if climbing:
            cx, cy, cb, cj = self._climb(obs, mx, my, boost, jump)
            return (cx, cy), cb, cj
        # unstick: commanded to move but barely moving -> jump + jet, then a detour
        hs = math.hypot(me["vel"][0], me["vel"][1])
        if n > 0.5 and hs < cfg.stuck_speed and me.get("grounded", True):
            self.slow_since = self.slow_since if self.slow_since is not None else t
            if t - self.slow_since > cfg.stuck_s:
                self.jet_until = t + 1.4
                self.stuck_hits = [s for s in self.stuck_hits if t - s < 6] + [t]
                self.slow_since = None
                if len(self.stuck_hits) >= 3:
                    self.detour_until = t + 1.5
                    self.detour_yaw = math.atan2(my, mx) + self.rng.choice((-1, 1)) * math.pi / 2
                    self.path = None
                    self.stuck_hits = []
        else:
            self.slow_since = None
        if t < self.detour_until:
            mx, my = math.cos(self.detour_yaw), math.sin(self.detour_yaw)
        if t < self.jet_until:
            if me.get("grounded", True):
                jump = True
            elif me["energy"] > 8:
                boost = True
        return (mx, my), boost, jump

    def _evade(self, obs, plan: Plan, mx: float, my: float, boost: bool, jump: bool):
        """Never stand still under fire. Whenever we shoot or are being shot at, run strafe legs across the
        threat's line of fire: random leg length so the enemy cannot time a lead, boost bursts and hops when
        energy allows, a radial push to hold a good range, and reverse instead of grinding into a wall.
        Standing still is kept only when we are truly hidden (COVER reached and no line of sight)."""
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        threat = self._threat(obs, plan)
        if threat is None:
            return mx, my, boost, jump
        if plan.mode in ("COVER", "COVERED", "PEEK"):
            return mx, my, boost, jump              # deliberate cover moves: no strafing on top
        by = yaw_to(pos, threat["pos"])
        d = dist2(pos, threat["pos"])
        if t >= self.strafe_until:
            self.strafe_sign = -self.strafe_sign
            # flank: lean the legs toward the threat's back (hits outside its front arc deal rear_mult),
            # but only with probability flank_bias so the pattern stays unpredictable
            if threat.get("kind") == "mech" and "aim" in threat and self.rng.random() < cfg.flank_bias:
                # rel: our angle around the threat, measured from its aim. Our strafe direction is
                # by + sign*pi/2 with by = yaw(us -> threat), so sign -1 walks us counter-clockwise around it
                # (rel grows) and +1 clockwise. Walk the way that takes us further from its aim.
                rel = wrap(yaw_to(threat["pos"], pos) - threat["aim"][0])
                self.strafe_sign = -1.0 if rel >= 0 else 1.0
            self.strafe_until = t + self.rng.uniform(cfg.strafe_leg_min_s, cfg.strafe_leg_max_s)
        side = by + self.strafe_sign * math.pi / 2
        zr = self._roof_z(me, plan.goal) if self.wm is not None else None
        if self.wm is not None and not self.wm.walk_ok(pos[0] + math.cos(side) * cfg.strafe_wall_probe,
                                                       pos[1] + math.sin(side) * cfg.strafe_wall_probe, zr):
            self.strafe_sign = -self.strafe_sign    # wall on this side: run the other way
            self.strafe_until = t + self.rng.uniform(cfg.strafe_leg_min_s, cfg.strafe_leg_max_s)
            side = by + self.strafe_sign * math.pi / 2
        px, py = math.cos(side), math.sin(side)
        # hold a range band: back off when too close, close in when out of reach
        lo, hi = self._range_band(me)
        radial = 0.0
        if zr is not None:
            pass                                    # on our roof: hold the height, strafe only
        elif plan.retreat or d < lo:
            radial = -0.8
        elif d > hi and plan.mode == "FIGHT":
            radial = 0.5
        rx, ry = math.cos(by) * radial, math.sin(by) * radial
        if plan.mode == "ROTATE":
            # the zone goal comes first; strafe on top of it
            mx, my = mx + px * 0.6, my + py * 0.6
        else:
            mx, my = mx * 0.4 + px + rx, my * 0.4 + py + ry
        energy = me["energy"]
        if threat.get("kind") == "mech" and energy > cfg.strafe_boost_energy:
            boost = True
        if zr is None and me.get("grounded", True) and energy > cfg.hop_energy and t >= self.hop_t:
            jump = True
            self.hop_t = t + self.rng.uniform(cfg.hop_every_s * 0.7, cfg.hop_every_s * 1.3)
        return mx, my, boost, jump

    def _threat(self, obs, plan: Plan) -> Optional[Dict[str, Any]]:
        """Who we should be dodging: the plan's target, else a mech that hit us lately or aims at us, else a drone
        that hit us lately."""
        if plan.target is not None and plan.target_kind in ("mech", "npc"):
            return plan.target
        t, pos = obs["t"], obs["self"]["pos"]
        hostile = self.mem.hostile_ids(t, self.cfg.provoked_s)
        best, bd = None, 1e18
        for m in obs["mechs"]:
            d = dist2(m["pos"], pos)
            aiming = m["kind"] == "mech" and d < 230 and abs(wrap(m["aim"][0] - yaw_to(m["pos"], pos))) < 0.1
            if (m["id"] in hostile or aiming) and d < bd:
                best, bd = m, d
        return best

    def _range_band(self, me) -> Tuple[float, float]:
        kinds = {w["kind"] for w in me["weapons"] if w}
        if "laser" in kinds:
            return self.cfg.range_laser
        if "lightning" in kinds:
            return self.cfg.range_lightning
        return self.cfg.range_gun

    def _steer(self, obs, goal: Tuple[float, float]) -> Tuple[float, float]:
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        d = dist2(pos, goal)
        arrive = 0.7 if self.last_plan is not None and self.last_plan.mode in ("PEEK", "COVER") else 2.0
        if d < arrive:
            return 0.0, 0.0
        wm = self.wm
        if wm is None or self._elevated(me) or wm.line_walkable((pos[0], pos[1]), goal):
            return (goal[0] - pos[0]) / d, (goal[1] - pos[1]) / d
        # (re)plan when the goal moved or the plan is stale; the search is resumable across ticks
        if (self.search_goal is None or dist2(self.search_goal, goal) > 6.0 or t - self.plan_t > cfg.replan_s) \
                and (self.search is None or self.search.done):
            self.search = PathSearch(wm, wm.nearest_free(pos[0], pos[1]), wm.nearest_free(goal[0], goal[1]))
            self.search_goal, self.plan_t = goal, t
        # spend only what is left of this decision's time on the search (target: under cfg.decide_ms)
        t0 = getattr(self, "_t0", time.perf_counter())
        deadline = min(t0 + cfg.decide_ms / 1000.0, time.perf_counter() + cfg.path_ms / 1000.0)
        if self.search is not None and not self.search.done and time.perf_counter() < deadline:
            if self.search.step(cfg.path_budget, deadline):
                self.path, self.path_goal, self.path_i = self.search.path, self.search_goal, 0
        if not self.path:
            return (goal[0] - pos[0]) / d, (goal[1] - pos[1]) / d
        # advance along the path: nearest point in a forward window, then aim a few cells ahead
        p = self.path
        lo, hi = self.path_i, min(self.path_i + 12, len(p))
        best = min(range(lo, hi), key=lambda i: dist2(p[i], pos)) if hi > lo else len(p) - 1
        self.path_i = best
        k = min(best + cfg.waypoint_lookahead, len(p) - 1)
        wx, wy = p[k] if k > best or dist2(p[-1], goal) > 3 else goal
        if k == len(p) - 1:
            wx, wy = goal
        dd = math.hypot(wx - pos[0], wy - pos[1])
        if dd < 1e-6:
            return 0.0, 0.0
        return (wx - pos[0]) / dd, (wy - pos[1]) / dd

    # ================================================================== aim + fire
    def _aim_fire(self, obs, plan: Plan, move) -> Tuple[Tuple[float, float], List[bool], bool]:
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        ws = me["weapons"]
        fire = [False, False]
        st = me["stats"]
        muzzle = [pos[0], pos[1], pos[2] + st.get("muzzle_height", 7.0)]
        cur_yaw, cur_pitch = me["aim"]
        tgt = plan.target
        if tgt is None:
            pre = self._preaim(obs, muzzle)
            pitch0 = 0.0
            if pre is not None:
                yaw, pitch0 = pre        # already on the most likely threat when the fight starts
            elif plan.face_bearing is not None:
                yaw = plan.face_bearing
            elif math.hypot(*move) > 0.1:
                yaw = math.atan2(move[1], move[0]) + cfg.scan_amp * math.sin(t * cfg.scan_rate)
            else:
                yaw = cur_yaw + 0.9   # standing still: keep turning to see all around
            # laser held with nothing to shoot: keep the trigger so a charge is not wasted
            for i, w in enumerate(ws):
                if w and w["kind"] == "laser" and w.get("charge", 0) > 0:
                    fire[i] = True
            gun = ws[0] if ws and ws[0] and ws[0]["kind"] == "gun" else None
            reload_ = bool(gun and gun.get("ammo", 12) < gun["stats"].get("mag", 12) * 0.5 and gun.get("reload", 0) == 0
                           and plan.mode in ("HOLD", "LOOT"))
            return (yaw, pitch0), fire, reload_

        # target centre of mass
        if plan.target_kind == "crate":
            tc = [tgt["pos"][0], tgt["pos"][1], tgt["pos"][2] + self.rules.get("crates", {}).get("height", 2.4) / 2]
            tv = [0.0, 0.0, 0.0]
            trad = self.rules.get("crates", {}).get("radius", 1.4)
        elif plan.target_kind == "npc":
            tc = [tgt["pos"][0], tgt["pos"][1], tgt["pos"][2] + self.rules.get("npc", {}).get("height", 3.5) / 2]
            tv = tgt.get("vel", [0, 0, 0])
            trad = self.rules.get("npc", {}).get("radius", 1.8)
        else:
            size = 1 + self.rules.get("cubes", {}).get("size_per_cube", 0.05) * tgt.get("cubes", 0)
            tc = [tgt["pos"][0], tgt["pos"][1], tgt["pos"][2] + self.mech_rules.get("height", 9.0) * size / 2]
            tv = tgt.get("vel", [0, 0, 0])
            trad = self.mech_rules.get("radius", 2.5) * size
        d = dist2(muzzle, tc)
        clear = self.wm.los(muzzle, tc) if self.wm is not None else True

        kinds = {w["kind"]: i for i, w in enumerate(ws) if w}
        laser_i = kinds.get("laser")
        mortar_i = kinds.get("mortar")
        aim_mode = "gun"
        if laser_i is not None and ws[laser_i]["cooldown"] <= 0.05 and d < ws[laser_i]["stats"].get("range", 280) and clear:
            aim_mode = "laser"
        elif mortar_i is not None and ws[mortar_i]["cooldown"] <= 0.05 and 30 < d < 220 and plan.target_kind != "crate":
            aim_mode = "mortar"

        moving = plan.target_kind in ("mech", "npc")
        zoff = tc[2] - tgt["pos"][2]
        if aim_mode == "laser":
            # hitscan: only the decision latency to cover (the beam leaves when we release next decision)
            pt = self.tracker.predict(tgt["id"], cfg.aim_latency_s * 2, muzzle, tgt["pos"], tv) if moving else list(tc)
            if moving:
                pt = [pt[0], pt[1], pt[2] + zoff]
            yaw, pitch = aim_at(muzzle, pt)
        elif aim_mode == "mortar":
            ms = ws[mortar_i]["stats"]
            sp, g = ms.get("speed", 72), ms.get("gravity", 22)
            p0 = mortar_pitch(d, tc[2] - muzzle[2], sp, g)
            if p0 is None:
                aim_mode = "gun"
            else:
                tt = mortar_time(d, p0, sp)
                pt = self.tracker.predict(tgt["id"], tt + cfg.aim_latency_s, muzzle, tgt["pos"], tv)
                d2 = dist2(muzzle, pt)
                p1 = mortar_pitch(d2, pt[2] - muzzle[2], sp, g) or p0
                yaw, pitch = yaw_to(muzzle, pt), p1
        if aim_mode == "gun":
            sp = ws[0]["stats"].get("speed", 252) if ws and ws[0] and ws[0]["kind"] == "gun" else 252
            if moving:
                pt, _ = self.tracker.intercept(tgt["id"], muzzle, sp, zoff, cfg.aim_latency_s, tgt["pos"], tv)
            else:
                pt = lead(muzzle, tc, tv, sp)
            yaw, pitch = aim_at(muzzle, pt)
        pitch = max(min(pitch, self.mech_rules.get("max_pitch", 1.3)), self.mech_rules.get("min_pitch", -0.7))

        yaw_err = abs(wrap(cur_yaw - yaw))
        pitch_err = abs(cur_pitch - pitch)
        tol = math.atan2(trad * 0.85, max(d, 1.0)) + 0.004
        on = yaw_err < tol and pitch_err < tol * 1.5
        for i, w in enumerate(ws):
            if not w:
                continue
            k, s = w["kind"], w["stats"]
            if k == "gun":
                fire[i] = clear and on and d < s.get("range", 230) and w.get("ammo", 1) > 0 and w.get("reload", 0) == 0
            elif k == "laser":
                charging = w.get("charge", 0) > 0
                full = w.get("charge", 0) >= s.get("charge", 0.75) - 0.02
                if aim_mode == "laser" or charging:
                    # hold to charge; let go (fire=False) once full and on target
                    fire[i] = not (full and on and clear)
            elif k == "lightning":
                cone = math.radians(s.get("cone_deg", 30)) / 2
                fire[i] = d < s.get("range", 45) * 0.95 and yaw_err < cone * 0.8 and me["energy"] > 12 and clear
            elif k == "mortar":
                own_splash = d < s.get("splash_radius", 7) * 2.5
                fire[i] = aim_mode == "mortar" and yaw_err < 0.03 and pitch_err < 0.03 and not own_splash
        gun = ws[0] if ws and ws[0] and ws[0]["kind"] == "gun" else None
        reload_ = bool(plan.mode == "COVERED" and gun and gun.get("reload", 0) == 0
                       and gun.get("ammo", 12) < gun["stats"].get("mag", 12))   # reload while hidden
        return (yaw, pitch), fire, reload_

    def _preaim(self, obs, muzzle) -> Optional[Tuple[float, float]]:
        """Aim at where the most likely threat will be: the closest visible mech (predicted half a second ahead),
        else a mech that hit us lately and has gone out of sight (extrapolated along its drift, at most
        preaim_hidden_s), so the torso is already on it when it reappears."""
        cfg, t, pos = self.cfg, obs["t"], obs["self"]["pos"]
        mechs = [m for m in obs["mechs"] if m["kind"] == "mech"]
        h = self.mech_rules.get("height", 9.0) / 2
        if mechs:
            m = min(mechs, key=lambda m: dist2(m["pos"], pos))
            p = self.tracker.predict(m["id"], 0.5, muzzle, m["pos"], m.get("vel"))
            return aim_at(muzzle, [p[0], p[1], p[2] + h])
        hostile = self.mem.hostile_ids(t, cfg.preaim_hostile_s)
        best = None
        for tid in hostile:
            s = self.tracker.last(tid)
            if s is None or tid >= 100:
                continue
            age = min(t - s[0], cfg.preaim_hidden_s)
            p = self.tracker.predict(tid, age, muzzle)
            d = dist2(p, pos)
            if best is None or d < best[0]:
                best = (d, p)
        if best is not None:
            p = best[1]
            return aim_at(muzzle, [p[0], p[1], p[2] + h])
        # nothing seen or hostile: face the most dangerous thing intel heard (footsteps round a corner, jets...)
        heard = [th for th in self.intel.active(t, pos, cfg.preaim_intel_conf) if th.mech_id is None
                 or t - th.t > 0.0]
        if heard:
            p = heard[0].pos
            return aim_at(muzzle, [p[0], p[1], p[2] + h])
        return None

    # ================================================================== offers + pickups
    def _offer(self, obs, act) -> None:
        off = obs.get("offer")
        if not off:
            return
        rank = {k: i for i, k in enumerate(self.cfg.upgrade_pref)}
        ch = off["choices"]
        act["pick"] = min(range(len(ch)), key=lambda i: rank.get(ch[i]["id"], 99))

    def _take(self, obs, act) -> None:
        me = obs["self"]
        pos = me["pos"]
        reach = self.rules.get("loot", {}).get("pickup_radius", 4.0) - 0.3
        ws = me["weapons"]
        for p in self.planner.wanted_pickups(obs):
            if dist2(p["pos"], pos) < reach and abs(p["pos"][2] - pos[2]) < 3.8:
                if len(ws) > 1 and ws[1] is not None:
                    if ws[1]["kind"] == "laser" and ws[1].get("charge", 0) > 0:
                        return
                    act["drop"] = 1
                act["take"] = p["id"]
                return
