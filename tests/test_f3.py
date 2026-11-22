"""F3: once a mech has been seen, no more farming except cubes within 15 m."""
import copy

from mechbot import MechBot


def base(observations, t=10.0):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = t
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    return o


def test_opener_until_contact_then_only_cubes_within_15m(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    p = o["self"]["pos"]
    o["cubes"] = [{"id": 5001, "pos": [p[0] + 50, p[1], p[2]]}]
    bot.act(o)
    assert "OPENER cube" in bot.last_plan.rationale
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 180, p[1] + 40, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["t"] += 0.1
    bot.act(o)                                           # first contact (a mech far off, not a threat)
    o["mechs"] = []
    o["t"] += 0.1
    bot.act(o)
    assert "cube" not in bot.last_plan.rationale         # the 50 m cube is no longer worth it
    o["cubes"] = [{"id": 5002, "pos": [p[0] + 10, p[1], p[2]]}]
    o["t"] += 0.1
    bot.act(o)
    assert "cube" in bot.last_plan.rationale             # 10 m: still taken
