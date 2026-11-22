"""C1 cube opener: first minute, drones from 50-110 m, crates, cubes, a laser; a mech attack overrides."""
import copy
import math

from mechbot import MechBot


def base(observations, t=10.0):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = t
    z = o["zone"]
    z.update(center=list(o["self"]["pos"][:2]), radius=600, shrink_start=200, shrink_end=260)
    return o


def drone(p, dx):
    return {"id": 105, "kind": "npc", "pos": [p[0] + dx, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
            "hp": 350, "max_hp": 350}


def test_shoots_a_drone_at_80m_without_closing(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    o["mechs"] = [drone(o["self"]["pos"], 80)]
    bot.act(o)
    p = bot.last_plan
    assert p.target_kind == "npc" and p.goal is None and "OPENER" in p.rationale


def test_backs_off_a_drone_inside_50m_and_closes_on_one_beyond_110m(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    me = o["self"]["pos"]
    o["mechs"] = [drone(me, 30)]
    bot.act(o)
    g = bot.last_plan.goal
    assert g is not None and g[0] < me[0]
    o["mechs"] = [drone(me, 118)]
    bot.act(o)
    g = bot.last_plan.goal
    assert g is not None and me[0] < g[0] < me[0] + 118 - 50


def test_cube_beats_crate_and_laser_is_taken(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    me = o["self"]["pos"]
    o["cubes"] = [{"id": 5001, "pos": [me[0] + 90, me[1], me[2]]}]
    o["crates"] = [{"id": 1001, "pos": [me[0] + 60, me[1], me[2]], "hp": 300}]
    bot.act(o)
    assert "cube" in bot.last_plan.rationale
    o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [me[0] + 85, me[1] + 5, me[2]]}]
    bot.act(o)
    assert "laser" in bot.last_plan.rationale


def test_a_mech_attack_overrides_the_opener_and_it_ends_at_60s(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    me = o["self"]["pos"]
    o["mechs"] = [drone(me, 80), {"id": 4, "kind": "mech", "pos": [me[0] - 70, me[1], me[2]], "vel": [0, 0, 0],
                                  "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": math.pi, "by": 4}]
    bot.act(o)
    assert bot.last_plan.target["id"] == 4
    bot = MechBot(hello)
    o = base(observations, t=61.0)
    o["mechs"] = [drone(o["self"]["pos"], 80)]
    bot.act(o)
    assert "OPENER" not in bot.last_plan.rationale


def test_c5_goes_140m_for_a_laser(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    me = o["self"]["pos"]
    o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [me[0] + 140, me[1], me[2]]}]
    bot.act(o)
    assert "laser" in bot.last_plan.rationale
