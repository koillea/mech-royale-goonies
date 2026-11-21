"""Position: perches, spot choice inside the next circle, climbing, staying on the roof under fire."""
import copy
import math

import pytest

from mechbot import BotConfig, MechBot
from mechbot.position import PositionPlanner


@pytest.fixture(scope="module")
def pp(wm, hello):
    return PositionPlanner(wm, BotConfig(), hello["config"])


def calm(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["self"]["energy"] = o["self"]["max_energy"] = 100
    return o


def test_perches_are_real_roofs(wm, pp, hello):
    assert len(pp.perches) > 20
    for p in pp.perches:
        assert all(abs(wm.roof[k] - p.top) < 0.3 for k in p.cells)
        assert all(not wm.blocked[k] for k in p.launch)
        assert p.height >= BotConfig().perch_min_height


def test_unreachable_towers_skipped(pp, observations):
    me = calm(observations)["self"]
    assert 45 < pp.climb_max(me) < 62          # protocol: about 60 m on a full 100-energy tank
    assert any(p.height > pp.climb_max(me) for p in pp.perches)   # the ~70 m towers exist but are not candidates


@pytest.mark.parametrize("radius", [380, 240, 140, 70])
def test_spot_inside_next_circle_and_prefers_height(pp, observations, radius):
    o = calm(observations)
    o["zone"].update(next_center=[-23.7, 2.2], next_radius=radius, shrink_end=o["t"] + 200)
    s = pp.choose(o, None, {})
    assert math.hypot(s.x + 23.7, s.y - 2.2) <= radius
    if radius >= 140:
        assert s.kind == "roof"


def test_tiny_circle_and_no_perches_fall_back_to_ground(pp, wm, hello, observations):
    o = calm(observations)
    o["zone"].update(next_center=[-23.7, 2.2], next_radius=25, shrink_end=o["t"] + 200)
    s = pp.choose(o, None, {})
    assert math.hypot(s.x + 23.7, s.y - 2.2) <= 25
    cfg = BotConfig(use_perches=False)
    s2 = PositionPlanner(wm, cfg, hello["config"]).choose(calm(observations), None, {})
    assert s2.kind == "ground"


def test_bad_perch_is_avoided(pp, observations):
    o = calm(observations)
    first = pp.choose(o, None, {})
    assert first.kind == "roof"
    second = pp.choose(o, None, {first.perch.pid: 1e9})
    assert second.perch is None or second.perch.pid != first.perch.pid


def _at_launch(hello, observations, energy):
    bot = MechBot(hello)
    o = calm(observations)
    bot.act(o)                                   # choose the spot
    sp = bot.spot
    assert sp.kind == "roof"
    lx, ly = bot.pos_planner.launch_for(sp.perch, o["self"]["pos"])
    o["self"]["pos"] = [lx, ly, bot.wm.ground(lx, ly)]
    o["self"]["vel"] = [0, 0, 0]
    o["self"]["grounded"] = True
    o["self"]["energy"] = energy
    o["tick"] += 2
    o["t"] += 0.1
    return bot, o, sp


def test_waits_for_energy_then_jets_up(hello, observations):
    bot, o, sp = _at_launch(hello, observations, energy=10)
    a = bot.act(o)
    assert bot.last_plan.mode == "CLIMB" and not a["jump"]
    o["self"]["energy"], o["tick"], o["t"] = 100, o["tick"] + 2, o["t"] + 0.1
    a = bot.act(o)
    assert a["jump"]
    o["self"]["grounded"], o["self"]["pos"][2] = False, sp.z - 5
    o["tick"], o["t"] = o["tick"] + 2, o["t"] + 0.1
    a = bot.act(o)
    assert a["boost"] and math.hypot(*a["move"]) > 0.9


def test_strafes_but_stays_on_roof_under_fire(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    bot.act(o)
    sp = bot.spot
    o["self"]["pos"] = [sp.x, sp.y, sp.z]
    o["self"]["grounded"] = True
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [sp.x + 70, sp.y, bot.wm.ground(sp.x + 70, sp.y)],
                   "vel": [0, 0, 0], "aim": [math.pi, 0.3], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    for k in range(40):
        o["tick"], o["t"] = o["tick"] + 2, o["t"] + 0.1
        o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
        a = bot.act(o)
        assert bot.last_plan.mode in ("FIGHT", "COVER")
        p = o["self"]["pos"]
        nxt = [p[0] + a["move"][0] * 1.2, p[1] + a["move"][1] * 1.2]
        assert bot.wm.walk_ok(nxt[0], nxt[1], sp.z), "strafe would walk off the roof"
        o["self"]["pos"] = [nxt[0], nxt[1], sp.z]
        o["self"]["vel"] = [a["move"][0] * 11.7, a["move"][1] * 11.7, 0]


@pytest.mark.parametrize("kind,dist,hostile,fights", [
    ("mech", 150, False, False),     # far and not shooting at us: watch, do not shoot
    ("mech", 60, False, True),       # inside the threat radius
    ("mech", 150, True, True),       # it shot us
    ("npc", 40, False, True),        # a drone inside its aggro range will shoot anyway
    ("npc", 80, False, False),
])
def test_fight_only_when_needed(hello, observations, kind, dist, hostile, fights):
    bot = MechBot(hello)
    o = calm(observations)
    me = o["self"]["pos"]
    o["mechs"] = [{"id": 9 if kind == "mech" else 105, "kind": kind, "pos": [me[0] + dist, me[1], me[2]],
                   "vel": [0, 0, 0], "aim": [0, 0], "hp": 350 if kind == "npc" else 1400,
                   "max_hp": 350 if kind == "npc" else 1400}]
    if kind == "mech":
        o["mechs"][0]["weapons"] = ["gun"]
    if hostile:
        o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    bot.act(o)
    assert (bot.last_plan.target is not None) == fights
