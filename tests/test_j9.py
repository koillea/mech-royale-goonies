"""J9: in the opener, a quiet mech within 90 m is fought, not farmed past."""
import copy

from mechbot import BotConfig, MechBot


def test_opener_fights_a_close_mech_first(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 10.0
    p = o["self"]["pos"]
    o["zone"].update(center=list(p[:2]), radius=600, shrink_start=200, shrink_end=260)
    o["cubes"] = [{"id": 5001, "pos": [p[0] - 40, p[1], p[2]]}]
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 70, p[1], p[2]], "vel": [0, 0, 0], "aim": [3.14, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    bot = MechBot(hello)
    bot.act(o)
    assert bot.last_plan.mode == "FIGHT" and bot.last_plan.target["id"] == 4
    old = MechBot(hello, BotConfig(opener_shoot_first=False))
    old.act(o)
    assert "OPENER cube" in old.last_plan.rationale
