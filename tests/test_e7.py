import copy

from mechbot import MechBot


def test_plating_before_armor(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[])
    o["offer"] = {"id": 1, "expires": 99, "choices": [{"id": "armor", "name": "", "desc": ""},
                                                      {"id": "servos", "name": "", "desc": ""},
                                                      {"id": "plating", "name": "", "desc": ""}]}
    assert MechBot(hello).act(o)["pick"] == 2
