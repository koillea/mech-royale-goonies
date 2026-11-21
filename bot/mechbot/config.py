"""Every tunable in one place. Each default cites the rule (protocol.md section) or the reasoning behind it.

Game numbers (speeds, ranges, damage) are NOT here: they are read live from `hello.config`, because
the protocol says balance changes between matches (section 6, `hello`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BotConfig:
    name: str = "goonies-survivor"

    # --- scoring: 16 - place, survival beats kills (section 4). House bots hunt the weakest entrant first,
    # so keeping HP high (regen needs 5 s without dealing or taking damage, section 7 Health) is the core plan.
    engage_range: float = 110.0          # shoot unprovoked only inside this (gun sound carries 320 m, section 8)
    engage_low_hp_frac: float = 0.4      # ...or at a visible enemy below this HP fraction within finish_range
    finish_range: float = 180.0
    provoked_s: float = 4.0              # an attacker stays "hostile" this long after its last hit on us
    retreat_hp_frac: float = 0.35        # below this, back away from the fight while still facing it (rear x1.5)

    # --- zone (section 9). Hold near the edge of the next circle on our side: shortest moves, fewest fights.
    hold_frac_early: float = 0.55        # target radius fraction of the next circle while it is large
    hold_frac_late: float = 0.35         # once next_radius <= late_radius
    late_radius: float = 70.0
    zone_margin: float = 12.0            # metres of safety inside the circle we must be in
    boost_when_late_s: float = 8.0       # boost if we would reach safety with less slack than this

    # --- loot (section 7 Weapon loot, section 10 Cubes)
    loot_radius: float = 55.0            # detour for a weapon or cube no further than this
    loot_until_t: float = 260.0          # stop looting once the circles are small and fights are constant
    crate_radius: float = 45.0
    crate_min_hp_frac: float = 0.7
    weapon_pref: List[str] = field(default_factory=lambda: ["laser", "lightning", "mortar"])
    drop_radius: float = 70.0            # contest a supply drop only if it lands this close

    # --- NPC drones aggro at 45 m with line of sight (section 7 NPC drones)
    npc_avoid: float = 55.0

    # --- upgrades: survival first (armor reduces weapon damage, plating raises max HP, nanites speed regen)
    upgrade_pref: List[str] = field(default_factory=lambda: [
        "armor", "plating", "nanites", "gun_rate", "gun_damage", "laser_damage", "laser_charge",
        "lightning_efficiency", "sensors", "gyros", "gun_mag", "gun_velocity", "servos", "capacitor",
        "reactor", "jets"])

    # --- movement
    stuck_speed: float = 2.0             # horizontal m/s below which a commanded move counts as blocked
    stuck_s: float = 0.6
    waypoint_lookahead: int = 4          # cells ahead on the A* path to steer at
    replan_s: float = 2.5
    path_budget: int = 2500              # A* node expansions per decision (about 10 ms)
    strafe_period_s: float = 1.3

    # --- sensing: sweep the 120 degree view cone so nobody reaches our back unseen (section 8 Vision)
    scan_amp: float = 1.4
    scan_rate: float = 0.9
