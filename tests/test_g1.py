"""G1: on the way to an opener cube, shoot a drone in view (50-110 m) without changing the goal."""
import copy

from mechbot import BotConfig, MechBot


def test_shoots_a_drone_while_walking_to_a_cube(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 10.0
    p = o["self"]["pos"]
    o["zone"].update(center=list(p[:2]), radius=600, shrink_start=200, shrink_end=260)
    o["cubes"] = [{"id": 5001, "pos": [p[0] + 30, p[1], p[2]]}]
    o["mechs"] = [{"id": 105, "kind": "npc", "pos": [p[0], p[1] + 90, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 350, "max_hp": 350}]
    bot = MechBot(hello)
    bot.act(o)
    pl = bot.last_plan
    assert "OPENER cube" in pl.rationale and pl.goal == (p[0] + 30, p[1])
    assert pl.target is not None and pl.target["id"] == 105
    off = MechBot(hello, BotConfig(opener_shoot_in_view=False))
    off.act(o)
    assert off.last_plan.target is None
