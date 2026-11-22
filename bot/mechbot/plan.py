"""Reason before acting: every decision starts with a Plan chosen from the observation.

The planner is a small set of ordered, explainable rules. Each Plan carries a `rationale`
string, drawn above the mech as a debug label, so every decision can be audited in replays.

Rule order (first match wins):
  1. ROTATE  - outside the zone, or we will be caught by the shrink: run (boost) to safety, shoot back on the way
  2. FIGHT   - a mech or drone hit us recently, or an enemy is close / weak enough to finish
  3. ALERT   - hit by something we cannot see: turn to face the bearing, keep moving
  4. LOOT    - safe and early: a better weapon, a cube, a crate, or a close uncontested supply drop
  5. HOLD    - walk to (or stay at) the hold point inside the next circle, scanning
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import BotConfig

Vec2 = Tuple[float, float]


@dataclass
class Plan:
    mode: str
    goal: Optional[Vec2] = None
    target: Optional[Dict[str, Any]] = None   # actor (mech/npc) or crate dict to shoot
    target_kind: str = ""                     # mech | npc | crate
    boost: bool = False
    retreat: bool = False
    face_bearing: Optional[float] = None
    take: Optional[Dict[str, Any]] = None     # weapon pickup we want
    rationale: str = ""
    collect: bool = False                     # E6: the goal is a cube to grab mid-fight (strafe less)


@dataclass
class Hold:
    """Where the position planner wants us (position.py), as seen by this decision."""
    goal: Optional[Vec2]                      # None = we are there (or climbing: movement handles it)
    spot: Vec2                                # the chosen spot itself
    perched: bool = False                     # standing on the chosen roof
    climbing: bool = False                    # at the wall, jetting up (or waiting for energy to)
    why: str = ""


def dist2(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def zone_now(z: Dict[str, Any], t: float) -> Tuple[Vec2, float]:
    """Circle we must be inside right now. Interpolates during the shrink window (section 9)."""
    c, r = z["center"], z["radius"]
    s, e = z["shrink_start"], z["shrink_end"]
    if t <= s or e <= s:
        return (c[0], c[1]), r
    f = min((t - s) / (e - s), 1.0)
    nc = z["next_center"]
    return (c[0] + (nc[0] - c[0]) * f, c[1] + (nc[1] - c[1]) * f), r + (z["next_radius"] - r) * f


class HeuristicPlanner:
    def __init__(self, cfg: BotConfig, rules: Dict[str, Any]):
        self.cfg = cfg
        self.rules = rules
        self.weapon_rank = {k: i for i, k in enumerate(cfg.weapon_pref)}

    # ------------------------------------------------------------------ zone
    def zone_goal(self, obs: Dict[str, Any], speed: float) -> Tuple[Optional[Vec2], bool, str]:
        cfg, me, z, t = self.cfg, obs["self"], obs["zone"], obs["t"]
        pos = me["pos"]
        nc, nr = z["next_center"], z["next_radius"]
        late = nr <= cfg.late_radius
        frac = cfg.hold_frac_late if late else cfg.hold_frac_early
        d = dist2(pos, nc)
        allowed = max(nr - cfg.zone_margin - 8.0, nr * frac)
        cc, cr = zone_now(z, t)
        outside_now = dist2(pos, cc) > cr - 3.0 or not me.get("in_zone", True)
        if nr <= 1.0:
            goal = (nc[0], nc[1])
        elif d <= allowed:
            goal = None
        else:
            ux, uy = (pos[0] - nc[0]) / d, (pos[1] - nc[1]) / d
            goal = (nc[0] + ux * nr * frac, nc[1] + uy * nr * frac)
        need = max(d - allowed, 0.0) / max(speed, 1.0)
        slack = z["shrink_end"] - t - need
        urgent = outside_now or (goal is not None and slack < cfg.boost_when_late_s)
        why = "outside zone" if outside_now else (f"shrink slack {slack:.0f}s" if urgent else "")
        return goal, urgent, why

    # ------------------------------------------------------------------ main
    def hold_urgency(self, obs: Dict[str, Any], hold: Hold, speed: float) -> Tuple[bool, str]:
        """Run (boost) if we are outside the zone now, or the shrink would catch us before we reach safety."""
        cfg, me, z, t = self.cfg, obs["self"], obs["zone"], obs["t"]
        pos = me["pos"]
        cc, cr = zone_now(z, t)
        if dist2(pos, cc) > cr - 3.0 or not me.get("in_zone", True):
            return True, "outside zone"
        nc, nr = z["next_center"], z["next_radius"]
        if dist2(pos, nc) <= max(nr - cfg.zone_margin, 0.0):
            return False, ""
        slack = z["shrink_end"] - t - dist2(pos, hold.spot) / max(speed, 1.0)
        if slack < cfg.boost_when_late_s:
            return True, f"shrink slack {slack:.0f}s"
        return False, ""

    def plan(self, obs: Dict[str, Any], mem: Any, hold: Optional[Hold] = None) -> Plan:
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        hp_frac = me["hp"] / max(me["max_hp"], 1.0)
        speed = me["stats"].get("walk_speed", 11.7)
        if hold is not None:
            goal = hold.goal
            urgent, zwhy = self.hold_urgency(obs, hold, speed)
            if urgent and goal is None and not hold.perched and not hold.climbing:
                goal = hold.spot
        else:
            goal, urgent, zwhy = self.zone_goal(obs, speed)
        perched = hold is not None and hold.perched
        busy = hold is not None and (hold.perched or hold.climbing)

        mechs = [m for m in obs["mechs"] if m["kind"] == "mech"]
        npcs = [m for m in obs["mechs"] if m["kind"] == "npc"]
        hostile = mem.hostile_ids(t, cfg.provoked_s)
        target, kind, why = self._pick_target(obs, mechs, npcs, hostile)

        if cfg.opener and t < cfg.opener_s and not urgent and (target is None or (kind == "mech" and target["id"] not in hostile)):
            op = self._opener(obs, npcs, goal)
            if op is not None:
                return op
        if urgent:
            if goal is None and not busy:
                goal = self._center(obs)
            return Plan("ROTATE", goal=goal, target=target, target_kind=kind,
                        boost=True, rationale=f"ROTATE {zwhy}" + (f" +{why}" if target else ""))
        if target is not None:
            retreat = (kind == "mech" and hp_frac < cfg.retreat_hp_frac
                       and target.get("hp", 0) >= me["hp"] and obs["alive"] > 2)
            cube = self._cube_near(obs, mem, cfg.cube_fight_radius) if not retreat else None
            if cube is not None:
                return Plan("FIGHT", goal=(cube["pos"][0], cube["pos"][1]), target=target, target_kind=kind,
                            collect=True, rationale=f"FIGHT {why} +cube")
            return Plan("FIGHT", goal=goal, target=target, target_kind=kind, retreat=retreat,
                        rationale=f"FIGHT {why}" + (" from roof" if perched else "") + (" retreat" if retreat else ""))
        bearing = mem.recent_damage_bearing(t, 3.0)
        if bearing is not None:
            return Plan("ALERT", goal=goal, face_bearing=bearing, rationale="ALERT hit from unseen")

        cube = self._cube_near(obs, mem, cfg.cube_radius) if not (hold is not None and hold.climbing) else None
        if cube is not None:
            return Plan("LOOT", goal=(cube["pos"][0], cube["pos"][1]),
                        rationale=f"LOOT cube {dist2(cube['pos'], pos):.0f}m (E6)")
        near_enemy = any(dist2(m["pos"], pos) < 120 for m in mechs)
        if t < cfg.loot_until_t and not near_enemy and not busy:
            lp = self._loot(obs, npcs, hp_frac, goal)
            if lp is not None:
                return lp
        if mechs:  # visible but not worth a fight: keep facing it so a hit lands on our front
            m = min(mechs, key=lambda m: dist2(m["pos"], pos))
            mode = "PERCH" if perched else ("CLIMB" if hold is not None and hold.climbing else "HOLD")
            return Plan(mode, goal=goal, face_bearing=math.atan2(m["pos"][1] - pos[1], m["pos"][0] - pos[0]),
                        rationale=f"{mode} watching {m['id']}")
        heard = mem.loud_bearing(t)
        where = (hold.why if hold is not None else "") or ("to point" if goal else "in place")
        mode = "PERCH" if perched else ("CLIMB" if hold is not None and hold.climbing else "HOLD")
        return Plan(mode, goal=goal, face_bearing=heard,
                    rationale=f"{mode} {where}" + (" heard" if heard is not None else ""))

    def _opener(self, obs, npcs, zgoal) -> Optional[Plan]:
        """C1: the first minute is for cubes. Cheapest next item: a visible cube, a laser, a drone (shot from
        50-110 m, outside its 45 m aggro), a crate. Only items inside the current circle."""
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        (cx, cy), cr = zone_now(obs["zone"], t)

        def inside(p) -> bool:
            return math.hypot(p[0] - cx, p[1] - cy) < cr - 8.0

        if cfg.fast_opener:
            obs, npcs = self._opener_memory(obs, npcs, pos, t)

        cands: List[Tuple[float, Plan]] = []
        for c in obs.get("cubes", []):
            d = dist2(c["pos"], pos)
            if d < cfg.opener_cube_radius and inside(c["pos"]):
                cands.append((d - 20, Plan("LOOT", goal=(c["pos"][0], c["pos"][1]), rationale=f"OPENER cube {d:.0f}m")))
        held = {w["kind"] for w in me["weapons"] if w}
        if "laser" not in held:
            for p in obs.get("pickups", []):
                d = dist2(p["pos"], pos)
                if p["kind"] == "laser" and d < cfg.opener_laser_radius and inside(p["pos"]):
                    cands.append((d - 30, Plan("LOOT", goal=(p["pos"][0], p["pos"][1]), take=p,
                                               rationale=f"OPENER laser {d:.0f}m")))
        lo, hi = cfg.opener_drone_band
        for n in npcs:
            d = dist2(n["pos"], pos)
            if n.get("_mem"):              # C7: seen during the sweep, out of view now: walk into the band
                if d < cfg.opener_drone_radius + 50 and inside(n["pos"]):
                    ux, uy = (pos[0] - n["pos"][0]) / max(d, 1e-6), (pos[1] - n["pos"][1]) / max(d, 1e-6)
                    g = (n["pos"][0] + ux * (hi - 15), n["pos"][1] + uy * (hi - 15)) if d > hi else None
                    if g is not None:
                        cands.append((d + 5, Plan("LOOT", goal=g, rationale=f"OPENER drone (seen) {d:.0f}m")))
                continue
            if d < cfg.opener_drone_radius and inside(n["pos"]):
                ux, uy = (pos[0] - n["pos"][0]) / max(d, 1e-6), (pos[1] - n["pos"][1]) / max(d, 1e-6)
                if d > hi:
                    g = (n["pos"][0] + ux * (hi - 15), n["pos"][1] + uy * (hi - 15))
                elif d < lo:
                    g = (n["pos"][0] + ux * (lo + 20), n["pos"][1] + uy * (lo + 20))
                else:
                    g = None
                cands.append((d, Plan("FIGHT", goal=g, target=n, target_kind="npc", rationale=f"OPENER drone {d:.0f}m")))
        for c in obs.get("crates", []):
            d = dist2(c["pos"], pos)
            if d < cfg.opener_crate_radius and inside(c["pos"]):
                g = (c["pos"][0], c["pos"][1]) if d > cfg.opener_crate_shoot else None
                if c.get("_mem"):
                    if g is not None:
                        cands.append((d + 20, Plan("LOOT", goal=g, rationale=f"OPENER crate (seen) {d:.0f}m")))
                    continue
                cands.append((d + 20, Plan("LOOT", goal=g, target=c, target_kind="crate",
                                           rationale=f"OPENER crate {d:.0f}m")))
        if not cands:
            return None
        return min(cands, key=lambda x: x[0])[1]

    def _opener_memory(self, obs, npcs, pos, t):
        """C7: items are listed only while in view and the torso sweeps, so remember cubes, crates, lasers and
        drones seen in the last opener_memory_s. Forget one once we are close to where it was and do not see
        it (collected, destroyed or moved). Remembered items carry _mem=True (no shooting what we cannot see)."""
        cfg = self.cfg
        if not hasattr(self, "seen_items"):
            self.seen_items = {}
        mem = self.seen_items
        vis = {}
        for kind, lst in (("cube", obs.get("cubes", [])), ("crate", obs.get("crates", [])),
                          ("pickup", obs.get("pickups", [])), ("npc", npcs)):
            for it in lst:
                vis[(kind, it["id"])] = it
                mem[(kind, it["id"])] = (dict(it), t)
        for k, (it, ts) in list(mem.items()):
            if k in vis:
                continue
            close = dist2(it["pos"], pos) < (6.0 if k[0] in ("cube", "pickup") else 25.0)
            if t - ts > cfg.opener_memory_s or (close and t - ts > 1.0):
                del mem[k]
        out = {"cubes": [], "crates": [], "pickups": []}
        new_npcs = list(npcs)
        for k, (it, ts) in mem.items():
            if k in vis:
                continue
            it = dict(it, _mem=True)
            if k[0] == "npc":
                new_npcs.append(it)
            else:
                out[k[0] + "s"].append(it)
        o2 = dict(obs)
        o2["cubes"] = list(obs.get("cubes", [])) + out["cubes"]
        o2["crates"] = list(obs.get("crates", [])) + out["crates"]
        o2["pickups"] = list(obs.get("pickups", [])) + out["pickups"]
        return o2, new_npcs

    def _cube_near(self, obs, mem, radius: float) -> Optional[Dict[str, Any]]:
        """E6: nearest cube within radius that lies inside the current zone, unless 2+ mechs are attacking us.
        Cubes are +4 % max HP (healing the difference) and +4 % damage each, and 1/3/6/10 cubes unlock upgrades;
        a killed mech drops all its cubes plus 2. Top bots on the cast carried 26 cubes and 2x our max armor."""
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        if not cfg.cube_hunt or not obs.get("cubes"):
            return None
        if len({i for i in mem.hostile_ids(t, 5.0) if i < 100}) >= 2:
            return None
        pos = me["pos"]
        (cx, cy), cr = zone_now(obs["zone"], t)
        best, bd = None, radius
        for c in obs["cubes"]:
            d = dist2(c["pos"], pos)
            if d < bd and math.hypot(c["pos"][0] - cx, c["pos"][1] - cy) < cr - 5.0:
                best, bd = c, d
        return best

    def _center(self, obs) -> Vec2:
        nc = obs["zone"]["next_center"]
        return (nc[0], nc[1])

    def _pick_target(self, obs, mechs, npcs, hostile) -> Tuple[Optional[Dict[str, Any]], str, str]:
        cfg, me = self.cfg, obs["self"]
        pos = me["pos"]
        best, best_score, why = None, -1e18, ""
        endgame = obs["alive"] <= cfg.endgame_alive
        radius = cfg.threat_radius_mech * (cfg.endgame_mult if endgame else 1.0)
        for m in mechs:
            d = dist2(m["pos"], pos)
            frac = m.get("hp", 1400) / max(m.get("max_hp", 1400), 1.0)
            is_hostile = m["id"] in hostile
            if not (is_hostile or d < radius):
                continue   # not a threat: watch it, do not shoot (shots give us away and reset our regen)
            score = (1000 if is_hostile else 0) - d - 400 * frac
            if score > best_score:
                best, best_score = m, score
                why = f"{m['id']} {'hostile' if is_hostile else 'inside'} {d:.0f}m"
        if best is not None:
            return best, "mech", why
        aggro = self.rules.get("npc", {}).get("aggro_range", 45.0)
        for n in sorted(npcs, key=lambda n: dist2(n["pos"], pos)):
            d = dist2(n["pos"], pos)
            if (n["id"] in hostile and d < 90) or d < aggro:
                return n, "npc", f"drone {n['id']} {d:.0f}m"
        return None, "", ""

    def _loot(self, obs, npcs, hp_frac, zgoal) -> Optional[Plan]:
        cfg, me = self.cfg, obs["self"]
        pos = me["pos"]

        def safe(p) -> bool:
            if any(dist2(n["pos"], p) < cfg.npc_avoid for n in npcs):
                return False
            if zgoal is not None:   # do not wander away from where the zone wants us
                return dist2(p, zgoal) < dist2(pos, zgoal) + cfg.loot_radius * 0.6
            return True

        want = self.wanted_pickups(obs)
        cands: List[Tuple[float, Plan]] = []
        for p in want:
            d = dist2(p["pos"], pos)
            if d < cfg.loot_radius and safe(p["pos"]):
                cands.append((d - 15, Plan("LOOT", goal=(p["pos"][0], p["pos"][1]), take=p,
                                           rationale=f"LOOT {p['kind']} {d:.0f}m")))
        for c in obs["cubes"]:
            d = dist2(c["pos"], pos)
            if d < cfg.loot_radius and safe(c["pos"]):
                cands.append((d - 10, Plan("LOOT", goal=(c["pos"][0], c["pos"][1]), rationale=f"LOOT cube {d:.0f}m")))
        for dr in obs.get("drops", []):
            d = dist2(dr["pos"], pos)
            if d < cfg.drop_radius and dr.get("holder") in (None, me["id"]) and dr["lands_in"] < d / 11.0 + 6:
                cands.append((d - 30, Plan("LOOT", goal=(dr["pos"][0], dr["pos"][1]), rationale=f"LOOT drop {d:.0f}m")))
        if hp_frac >= cfg.crate_min_hp_frac:
            for c in obs["crates"]:
                d = dist2(c["pos"], pos)
                if d < cfg.crate_radius and safe(c["pos"]):
                    cands.append((d, Plan("LOOT", goal=(c["pos"][0], c["pos"][1]) if d > 25 else None, target=c,
                                          target_kind="crate", rationale=f"LOOT crate {d:.0f}m")))
        if not cands:
            return None
        return min(cands, key=lambda x: x[0])[1]

    def wanted_pickups(self, obs) -> List[Dict[str, Any]]:
        """Pickups that improve our loadout: fill an empty slot, or replace a worse slot-1 weapon."""
        ws = obs["self"]["weapons"]
        held = {w["kind"] for w in ws if w}
        slot1 = ws[1]["kind"] if len(ws) > 1 and ws[1] else None
        r1 = self.weapon_rank.get(slot1, 99) if slot1 else 99
        out = []
        for p in obs["pickups"]:
            k = p["kind"]
            if k == "gun" or k in held or k not in self.weapon_rank:
                continue
            if slot1 is None or self.weapon_rank[k] < r1:
                out.append(p)
        return out
