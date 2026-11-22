"""J2: never take a mortar; drop one we hold."""
import copy

from mechbot import MechBot


def test_no_mortar(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    o["self"]["weapons"][1] = None
    o["pickups"] = [{"id": 8001, "kind": "mortar", "pos": [p[0] + 1, p[1], p[2]]}]
    a = bot.act(o)
    assert "take" not in a
    o["pickups"] = []
    o["self"]["weapons"][1] = {"kind": "mortar", "cooldown": 0.0, "stats": {"cooldown": 2.6}}
    o["t"] += 0.1
    o["tick"] += 2
    a = bot.act(o)
    assert a.get("drop") == 1 and "take" not in a
