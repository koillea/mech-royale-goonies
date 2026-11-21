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
    # Fight only when we must: a mech that hit us, a mech inside threat_radius_mech, or a drone inside its own
    # aggro range (npc.aggro_range, 45 m, section 7 NPC drones) or one that hit us. Everything else is watched.
    threat_radius_mech: float = 90.0
    endgame_alive: int = 3               # with this few mechs left, widen the mech radius by endgame_mult
    endgame_mult: float = 1.5
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

    # --- position (position.py). Height first: roofs see further, shoot down, sit out of drone reach.
    use_perches: bool = True
    perch_min_height: float = 6.0        # lower roofs give little advantage
    perch_min_cells: int = 6             # interior roof cells (3 m each) needed to strafe without falling off
    climb_safety: float = 0.8            # use 80 % of the tank's theoretical climb (protocol: ~60 m on 100 energy)
    climb_energy_margin: float = 15.0    # wait at the wall until energy covers the climb plus this
    climb_timeout_s: float = 7.0         # give up on a roof after this long trying; avoid it for bad_perch_s
    bad_perch_s: float = 60.0
    respot_s: float = 8.0                # re-score spots this often (hysteresis keeps us put unless clearly better)
    ground_stride: int = 4               # sample ground spots at least every 4 cells (12 m)...
    ground_samples: int = 1200           # ...and widen the stride so a big circle stays under this many
    height_cap: float = 30.0
    w_height: float = 1.2
    w_room: float = 0.3
    w_cover: float = 0.5
    w_center: float = 0.7
    w_travel: float = 1.0
    w_crowd: float = 0.8
    w_npc: float = 0.6
    w_stay: float = 0.25

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
    path_budget: int = 2500              # A* node expansions per 10 ms of time left in the decision
    decide_ms: float = 22.0              # aim to finish every decision by this (budget is 50 ms on 1 CPU)
    # --- evasion: never stand still under fire. A gun bullet takes ~0.4 s to cross 100 m (252 m/s), and the
    # enemy leads on our current velocity, so legs of random length (reversals it cannot time) at boost speed
    # (19.5 vs 11.7 m/s, section 7 Movement) make its lead wrong. Boost drains 17/s and energy regenerates
    # 18/s after 0.6 s, so bursts above a reserve keep energy for unsticking and jets.
    strafe_leg_min_s: float = 0.8
    strafe_leg_max_s: float = 2.0
    strafe_wall_probe: float = 6.0       # metres: a wall this close on the strafe side reverses the leg
    strafe_boost_energy: float = 45.0    # boost while strafing only above this energy
    hop_energy: float = 60.0             # occasional jump (vertical 11 m/s) to spoil the enemy's pitch lead
    hop_every_s: float = 2.5
    # range bands (min, max metres) per best weapon held: gun spread is 0.6 deg (about 1 m at 100 m) and
    # range 230; laser reaches 280 and needs no lead; lightning reaches only 45.
    range_gun: tuple = (35.0, 130.0)
    range_laser: tuple = (60.0, 200.0)
    range_lightning: tuple = (12.0, 38.0)

    # --- sensing: sweep the 120 degree view cone so nobody reaches our back unseen (section 8 Vision)
    scan_amp: float = 1.4
    scan_rate: float = 0.9
