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
    def plan(self, obs: Dict[str, Any], mem: Any) -> Plan:
        cfg, me, t = self.cfg, obs["self"], obs["t"]
        pos = me["pos"]
        hp_frac = me["hp"] / max(me["max_hp"], 1.0)
        speed = me["stats"].get("walk_speed", 11.7)
        goal, urgent, zwhy = self.zone_goal(obs, speed)

        mechs = [m for m in obs["mechs"] if m["kind"] == "mech"]
        npcs = [m for m in obs["mechs"] if m["kind"] == "npc"]
        hostile = mem.hostile_ids(t, cfg.provoked_s)
        target, kind, why = self._pick_target(obs, mechs, npcs, hostile)

        if urgent:
            return Plan("ROTATE", goal=goal or self._center(obs), target=target, target_kind=kind,
                        boost=True, rationale=f"ROTATE {zwhy}" + (f" +{why}" if target else ""))
        if target is not None:
            retreat = (kind == "mech" and hp_frac < cfg.retreat_hp_frac
                       and target.get("hp", 0) >= me["hp"] and obs["alive"] > 2)
            return Plan("FIGHT", goal=goal, target=target, target_kind=kind, retreat=retreat,
                        rationale=f"FIGHT {why}" + (" retreat" if retreat else ""))
        bearing = mem.recent_damage_bearing(t, 3.0)
        if bearing is not None:
            return Plan("ALERT", goal=goal, face_bearing=bearing, rationale="ALERT hit from unseen")

        near_enemy = any(dist2(m["pos"], pos) < 120 for m in mechs)
        if t < cfg.loot_until_t and not near_enemy:
            lp = self._loot(obs, npcs, hp_frac, goal)
            if lp is not None:
                return lp
        if mechs:  # visible but not worth a fight: keep facing it so a hit lands on our front
            m = min(mechs, key=lambda m: dist2(m["pos"], pos))
            return Plan("HOLD", goal=goal, face_bearing=math.atan2(m["pos"][1] - pos[1], m["pos"][0] - pos[0]),
                        rationale=f"HOLD watching {m['id']}")
        heard = mem.loud_bearing(t)
        return Plan("HOLD", goal=goal, face_bearing=heard,
                    rationale="HOLD" + (" to point" if goal else " in place") + (" heard" if heard is not None else ""))

    def _center(self, obs) -> Vec2:
        nc = obs["zone"]["next_center"]
        return (nc[0], nc[1])

    def _pick_target(self, obs, mechs, npcs, hostile) -> Tuple[Optional[Dict[str, Any]], str, str]:
        cfg, me = self.cfg, obs["self"]
        pos = me["pos"]
        best, best_score, why = None, -1e18, ""
        endgame = obs["alive"] <= 3
        for m in mechs:
            d = dist2(m["pos"], pos)
            frac = m.get("hp", 1400) / max(m.get("max_hp", 1400), 1.0)
            is_hostile = m["id"] in hostile
            if not (is_hostile or d < cfg.engage_range or (frac < cfg.engage_low_hp_frac and d < cfg.finish_range)
                    or (endgame and d < 220)):
                continue
            score = (1000 if is_hostile else 0) - d - 400 * frac
            if score > best_score:
                best, best_score = m, score
                why = f"{m['id']} {'hostile' if is_hostile else 'close' if d < cfg.engage_range else 'weak'} {d:.0f}m"
        if best is not None:
            return best, "mech", why
        for n in npcs:
            if n["id"] in hostile and dist2(n["pos"], pos) < 90:
                return n, "npc", f"drone {n['id']}"
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
                    cands.append((d, Plan("LOOT", goal=None if d < 25 else (c["pos"][0], c["pos"][1]), target=c,
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
