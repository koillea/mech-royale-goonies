"""C3 heal break: 2+ attackers and HP < 50 %: cover, facing them, no fire, until 5 s without damage."""
import copy

from mechbot import MechBot


def setup(hello, observations, hp):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    o["self"]["hp"] = hp
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["mechs"] = [{"id": i, "kind": "mech", "pos": [p[0] + 60, p[1] + 10 * (i - 4), p[2]], "vel": [0, 0, 0],
                   "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]} for i in (4, 5)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": i} for i in (4, 5)]
    return bot, o


def test_breaks_off_below_half_with_two_attackers_and_resumes(hello, observations):
    bot, o = setup(hello, observations, 600)
    a = bot.act(o)
    assert bot.last_plan.mode == "COVER" and "HEAL" in bot.last_plan.rationale
    assert a["fire"] == [False, False] and bot.last_plan.target is not None
    o["events"] = []
    o["t"] += 3.0
    o["tick"] += 60
    bot.act(o)
    assert bot.healing                                   # only 3 s quiet
    o["t"] += 2.5
    o["tick"] += 50
    bot.act(o)
    assert not bot.healing and "HEAL" not in bot.last_plan.rationale


def test_no_break_above_half(hello, observations):
    bot, o = setup(hello, observations, 900)
    bot.act(o)
    assert "HEAL" not in bot.last_plan.rationale and not bot.healing
