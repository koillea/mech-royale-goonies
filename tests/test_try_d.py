import copy

from mechbot import MechBot


def calm(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    return o


def test_grabs_close_laser_skips_far_or_contested_and_repicks(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    bot.act(o)
    p = o["self"]["pos"]
    o["pickups"] = [{"id": 8011, "kind": "laser", "pos": [p[0] + 25, p[1], p[2]]}]
    o["t"] += 0.1; o["tick"] += 2
    bot.act(o)
    assert bot.last_plan.take is not None and bot.last_plan.take["id"] == 8011
    o["pickups"] = [{"id": 8013, "kind": "laser", "pos": [p[0] + 25, p[1], p[2]]}]
    o["mechs"] = [{"id": 6, "kind": "mech", "pos": [p[0] + 60, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["t"] += 0.1; o["tick"] += 2
    bot.act(o)
    assert not (bot.last_plan.take and bot.last_plan.take["id"] == 8013)
    o["mechs"], o["pickups"] = [], []
    o["events"] = [{"type": "took", "id": 8011, "kind": "laser", "slot": 1}]
    before = bot.spot_t
    o["t"] += 0.1; o["tick"] += 2
    bot.act(o)
    assert bot.spot_t > before
