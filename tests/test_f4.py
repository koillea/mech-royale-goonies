"""F4: a mech closer than the range band: hold our ground and strafe, do not back off."""
import copy

from mechbot import BotConfig, MechBot


def run(hello, observations, cfg):
    bot = MechBot(hello, cfg)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 20, p[1], p[2]], "vel": [0, 0, 0], "aim": [3.14, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    xs = []
    for _ in range(10):
        a = bot.act(o)
        xs.append(a["move"][0])                           # the attacker is 20 m due east
        o["t"] += 0.1
        o["tick"] += 2
    return sum(xs) / len(xs)


def test_holds_instead_of_backing_off(hello, observations):
    assert run(hello, observations, BotConfig(no_spacing=False)) < -0.3    # F1: backs off west
    assert run(hello, observations, BotConfig()) > -0.15                  # F4: holds (strafes north/south)
