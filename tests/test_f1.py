"""F1 no retreat: at low HP, losing, against a laser: keep fighting, no COVER, no backing off."""
import copy

from mechbot import MechBot


def test_low_hp_against_a_laser_keeps_fighting(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["self"]["hp"] = 300
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 100, p[1], p[2]], "vel": [0, 0, 0], "aim": [3.14, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun", "laser"]}]
    o["events"] = [{"type": "damaged", "amount": 120, "weapon": "laser", "bearing": 0.0, "by": 4}]
    pushes = []
    for _ in range(10):
        a = bot.act(o)
        assert bot.last_plan.mode == "FIGHT" and not bot.last_plan.retreat
        pushes.append(a["move"][0])                       # the attacker is due east
        o["t"] += 0.1
        o["tick"] += 2
    assert sum(pushes) / len(pushes) > -0.2              # not running away west
