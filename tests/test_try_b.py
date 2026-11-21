import copy

from mechbot import MechBot


def test_does_not_shoot_crates(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    o["crates"] = [{"id": 1001, "pos": [p[0] + 15, p[1], p[2]], "hp": 300}]
    a = bot.act(o)
    assert bot.last_plan.target is None and not any(a["fire"])
