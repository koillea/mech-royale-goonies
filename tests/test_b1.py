"""B1 roof sniper: from a roof, engage any visible mech in weapon range; stay up for cubes."""
import copy

from mechbot import MechBot


def test_perched_engages_a_mech_at_180m_and_ignores_cubes(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    bot.act(o)
    sp = bot.spot
    assert sp.kind == "roof" and sp.perch.height >= 12
    o["self"]["pos"] = [sp.x, sp.y, sp.z]
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [sp.x + 180, sp.y, bot.wm.ground(sp.x + 180, sp.y)],
                   "vel": [0, 0, 0], "aim": [3.1, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["t"] += 0.1
    o["tick"] += 2
    bot.act(o)
    assert bot.last_plan.target is not None and bot.last_plan.target["id"] == 4
    o["mechs"] = []
    o["cubes"] = [{"id": 5001, "pos": [sp.x + 30, sp.y, bot.wm.ground(sp.x + 30, sp.y)]}]
    o["t"] += 0.1
    o["tick"] += 2
    bot.act(o)
    assert "cube" not in bot.last_plan.rationale
