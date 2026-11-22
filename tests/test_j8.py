"""J8: opener: a drone in view beats a closer crate."""
import copy

from mechbot import BotConfig, MechBot


def test_drone_before_crate(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 10.0
    p = o["self"]["pos"]
    o["zone"].update(center=list(p[:2]), radius=600, shrink_start=200, shrink_end=260)
    o["crates"] = [{"id": 1001, "pos": [p[0] + 30, p[1], p[2]], "hp": 300}]
    o["mechs"] = [{"id": 105, "kind": "npc", "pos": [p[0], p[1] + 100, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 350, "max_hp": 350}]
    bot = MechBot(hello)
    bot.act(o)
    assert bot.last_plan.target_kind == "npc"
    old = MechBot(hello, BotConfig(drones_before_crates=False))
    old.act(o)
    assert old.last_plan.target_kind == "crate"
