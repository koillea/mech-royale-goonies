"""B4 roof first: on the way to a roof, do not start a fight with a mech that has not hit us."""
import copy
import math

from mechbot import MechBot


def _setup(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    bot.act(o)
    assert bot.spot.kind == "roof"
    h = bot._hold(o)
    assert h.to_roof and not h.perched
    p = o["self"]["pos"]
    x, y = p[0] + 60, p[1]
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [x, y, bot.wm.ground(x, y)],
                   "vel": [0, 0, 0], "aim": [3.1, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["t"] += 0.1
    o["tick"] += 2
    return bot, o


def test_ignores_a_quiet_mech_at_60m_on_the_way_up(hello, observations):
    bot, o = _setup(hello, observations)
    bot.act(o)
    assert bot.last_plan.target is None


def test_fights_back_when_hit_on_the_way_up(hello, observations):
    bot, o = _setup(hello, observations)
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    bot.act(o)
    assert bot.last_plan.target is not None and bot.last_plan.target["id"] == 4
