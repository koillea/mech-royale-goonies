"""E6: collect cubes all match: after kills, from roofs, with mechs near, but not with 2+ attackers."""
import copy
import math

from mechbot import BotConfig, MechBot


def calm(observations, t=300.0):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = t
    p = o["self"]["pos"]
    o["zone"].update(center=[p[0], p[1]], radius=380, next_center=[p[0], p[1]], next_radius=240,
                     shrink_start=t + 60, shrink_end=t + 100, dps=35)   # we are safely inside at time t
    return o


def mech(i, p, dx, dy=0.0, hp=1400):
    return {"id": i, "kind": "mech", "pos": [p[0] + dx, p[1] + dy, p[2]], "vel": [0, 0, 0],
            "aim": [math.atan2(-dy, -dx), 0], "hp": hp, "max_hp": 1400, "weapons": ["gun"]}


def test_late_game_cube_with_a_mech_watching(hello, observations):
    bot = MechBot(hello, BotConfig(full_offense=False, strafe_leg_min_s=0.8, strafe_leg_max_s=2.0))   # O2 fights it instead (test_o2.py)
    o = calm(observations)                      # after the old 260 s loot limit
    p = o["self"]["pos"]
    o["cubes"] = [{"id": 5001, "pos": [p[0] + 30, p[1], p[2]]}]
    o["mechs"] = [mech(4, p, 0, 150)]           # visible but not fighting us
    bot.act(o)
    assert bot.last_plan.mode == "LOOT" and "cube" in bot.last_plan.rationale


def test_mid_fight_one_attacker_steps_onto_cube(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    p = o["self"]["pos"]
    o["mechs"] = [mech(9, p, 70)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    o["cubes"] = [{"id": 5002, "pos": [p[0], p[1] + 15, p[2]]}]
    a = bot.act(o)
    assert bot.last_plan.mode == "FIGHT" and bot.last_plan.collect and a["move"][1] > 0.5


def test_no_cube_runs_with_two_attackers(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    p = o["self"]["pos"]
    o["mechs"] = [mech(9, p, 70), mech(10, p, -70)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9},
                   {"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 3.1, "by": 10}]
    o["cubes"] = [{"id": 5003, "pos": [p[0], p[1] + 15, p[2]]}]
    bot.act(o)
    assert not bot.last_plan.collect and "cube" not in bot.last_plan.rationale


def test_cube_outside_the_zone_is_ignored(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    p = o["self"]["pos"]
    o["zone"].update(center=[p[0], p[1]], radius=40, next_center=[p[0], p[1]], next_radius=20,
                     shrink_start=o["t"] + 100, shrink_end=o["t"] + 150)
    o["cubes"] = [{"id": 5004, "pos": [p[0] + 50, p[1], p[2]]}]
    bot.act(o)
    assert "cube" not in bot.last_plan.rationale
