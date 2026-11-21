"""MechBot: plan(obs) -> execute(plan) every decision.

Life cycle per decision (10 per match-second, 50 ms budget):
  ingest events into Memory -> HeuristicPlanner.plan() -> movement (A* path, strafe, dodge, unstick)
  -> aim and triggers per weapon -> upgrade pick and pickup take -> action dict.
"""
from __future__ import annotations

import math
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .ballistics import aim_at, lead, mortar_pitch, mortar_time, wrap, yaw_to
from .config import BotConfig
from .plan import HeuristicPlanner, Plan, dist2
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

    def ingest(self, obs: Dict[str, Any]) -> None:
        t = obs["t"]
        for e in obs.get("events", []):
            if e.get("type") == "damaged":
                self.took_damage_t = t
                if e.get("by") is not None:
                    self.attackers[int(e["by"])] = t
                    self.dmg_by = int(e["by"])
                if e.get("bearing") is not None:
                    self.dmg_bearing, self.dmg_t = e["bearing"], t
        for s in obs.get("sounds", []):
            if s["kind"] in LOUD and s["dist"] in ("near", "mid"):
                self.sounds.append((t - s.get("age", 0), s["bearing"], s["dist"]))
        self.sounds = [s for s in self.sounds if t - s[0] < 3.0][-20:]

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
        self.cover_t = -1e9
        self.cover_from: Optional[int] = None
        log(f"{self.name}: init {time.time() - t0:.2f}s map={'ok' if self.wm else 'none'}")

    # ================================================================== decision
    def act(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        self.mem.ingest(obs)
        plan = self.planner.plan(obs, self.mem)
        self._maybe_cover(obs, plan)
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

    # ================================================================== cover
    def _maybe_cover(self, obs, plan: Plan) -> None:
        """Break line of sight when a fight is bad for us: a laser outranges our gun, or we are losing on HP."""
        if self.wm is None or plan.mode != "FIGHT" or plan.target_kind != "mech":
            return
        me, tgt, t = obs["self"], plan.target, obs["t"]
        d = dist2(me["pos"], tgt["pos"])
        laser = "laser" in tgt.get("weapons", []) and not any(w and w["kind"] == "laser" for w in me["weapons"])
        losing = me["hp"] < tgt.get("hp", 1400) * 0.8
        if not (plan.retreat or (laser and d > 60) or (losing and d > 45)):
            return
        if self.cover_from != tgt["id"] or t - self.cover_t > 1.0:
            self.cover = self._find_cover(me, tgt)
            self.cover_t, self.cover_from = t, tgt["id"]
        if self.cover is not None:
            plan.goal = self.cover
            plan.retreat = False
            plan.boost = True
            plan.mode = "COVER"
            plan.rationale = f"COVER from {tgt['id']} {d:.0f}m"

    def _find_cover(self, me, tgt) -> Optional[Tuple[float, float]]:
        wm, pos = self.wm, me["pos"]
        eye = [tgt["pos"][0], tgt["pos"][1], tgt["pos"][2] + self.mech_rules.get("eye_height", 8.0)]
        best, bd = None, 1e18
        away = yaw_to(tgt["pos"], pos)
        for r in (6.0, 10.0, 15.0, 21.0, 28.0, 36.0):
            for k in range(16):
                a = away + (k - 8) * math.pi / 8
                x, y = pos[0] + math.cos(a) * r, pos[1] + math.sin(a) * r
                if not wm.free(x, y):
                    continue
                g = wm.ground(x, y)
                if wm.los(eye, [x, y, g + 8.5]):
                    continue
                cost = r + 0.3 * abs(wrap(a - away)) * r
                if cost < bd and wm.line_walkable((pos[0], pos[1]), (x, y)):
                    best, bd = (x, y), cost
            if best is not None:
                return best
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

        # wall avoidance on the grid: if the cell a few metres ahead is solid, rotate toward free space
        n = math.hypot(mx, my)
        if n > 1e-6:
            mx, my = mx / n, my / n
            if self.wm is not None and not self.wm.free(pos[0] + mx * 4.0, pos[1] + my * 4.0) and t > self.jet_until:
                base = math.atan2(my, mx)
                for da in (0.4, -0.4, 0.8, -0.8, 1.2, -1.2, 1.6, -1.6):
                    a = base + da
                    if self.wm.free(pos[0] + math.cos(a) * 4.0, pos[1] + math.sin(a) * 4.0):
                        mx, my = math.cos(a), math.sin(a)
                        break

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
        if plan.mode == "COVER" and plan.goal is not None and dist2(pos, plan.goal) < 3.0 and self.wm is not None:
            eye = [threat["pos"][0], threat["pos"][1], threat["pos"][2] + self.mech_rules.get("eye_height", 8.0)]
            if not self.wm.los(eye, [pos[0], pos[1], pos[2] + 8.5]):
                return mx, my, boost, jump          # hidden: stay put, regen
            self.cover_t = -1e9                     # cover is not hiding us: search again next decision
        by = yaw_to(pos, threat["pos"])
        d = dist2(pos, threat["pos"])
        if t >= self.strafe_until:
            self.strafe_sign = -self.strafe_sign
            self.strafe_until = t + self.rng.uniform(cfg.strafe_leg_min_s, cfg.strafe_leg_max_s)
        side = by + self.strafe_sign * math.pi / 2
        if self.wm is not None and not self.wm.free(pos[0] + math.cos(side) * cfg.strafe_wall_probe,
                                                     pos[1] + math.sin(side) * cfg.strafe_wall_probe):
            self.strafe_sign = -self.strafe_sign    # wall on this side: run the other way
            self.strafe_until = t + self.rng.uniform(cfg.strafe_leg_min_s, cfg.strafe_leg_max_s)
            side = by + self.strafe_sign * math.pi / 2
        px, py = math.cos(side), math.sin(side)
        # hold a range band: back off when too close, close in when out of reach
        lo, hi = self._range_band(me)
        radial = 0.0
        if plan.retreat or d < lo:
            radial = -0.8
        elif d > hi and plan.mode == "FIGHT":
            radial = 0.5
        rx, ry = math.cos(by) * radial, math.sin(by) * radial
        if plan.mode in ("ROTATE", "COVER"):
            # the zone or cover goal comes first; strafe on top of it
            mx, my = mx + px * 0.6, my + py * 0.6
        else:
            mx, my = mx * 0.4 + px + rx, my * 0.4 + py + ry
        energy = me["energy"]
        if threat.get("kind") == "mech" and energy > cfg.strafe_boost_energy:
            boost = True
        if me.get("grounded", True) and energy > cfg.hop_energy and t >= self.hop_t:
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
        if d < 2.0:
            return 0.0, 0.0
        wm = self.wm
        if wm is None or wm.line_walkable((pos[0], pos[1]), goal):
            return (goal[0] - pos[0]) / d, (goal[1] - pos[1]) / d
        # (re)plan when the goal moved or the plan is stale; the search is resumable across ticks
        if (self.search_goal is None or dist2(self.search_goal, goal) > 6.0 or t - self.plan_t > cfg.replan_s) \
                and (self.search is None or self.search.done):
            self.search = PathSearch(wm, wm.nearest_free(pos[0], pos[1]), wm.nearest_free(goal[0], goal[1]))
            self.search_goal, self.plan_t = goal, t
        if self.search is not None and not self.search.done:
            if self.search.step(cfg.path_budget):
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
            if plan.face_bearing is not None:
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
            return (yaw, 0.0), fire, reload_

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

        if aim_mode == "laser":
            pt = [tc[0] + tv[0] * 0.1, tc[1] + tv[1] * 0.1, tc[2]]
            yaw, pitch = aim_at(muzzle, pt)
        elif aim_mode == "mortar":
            ms = ws[mortar_i]["stats"]
            sp, g = ms.get("speed", 72), ms.get("gravity", 22)
            p0 = mortar_pitch(d, tc[2] - muzzle[2], sp, g)
            if p0 is None:
                aim_mode = "gun"
            else:
                tt = mortar_time(d, p0, sp)
                pt = [tgt["pos"][0] + tv[0] * tt, tgt["pos"][1] + tv[1] * tt, tgt["pos"][2]]
                d2 = dist2(muzzle, pt)
                p1 = mortar_pitch(d2, pt[2] - muzzle[2], sp, g) or p0
                yaw, pitch = yaw_to(muzzle, pt), p1
        if aim_mode == "gun":
            sp = ws[0]["stats"].get("speed", 252) if ws and ws[0] and ws[0]["kind"] == "gun" else 252
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
        return (yaw, pitch), fire, False

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
