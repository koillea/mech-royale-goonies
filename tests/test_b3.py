"""B3 chokepoint defence: hold a walled-in ground spot and fight from it."""
import copy
import math

from mechbot import MechBot


def test_spot_is_a_chokepoint_and_a_fight_holds_it(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    bot.act(o)
    sp = bot.spot
    assert sp.kind == "ground" and bot.wm.cover[bot.wm.idx(sp.x, sp.y)] >= bot.cfg.choke_min_cover
    o["self"]["pos"] = [sp.x + 2, sp.y, sp.z]
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [sp.x + 70, sp.y + 10, sp.z], "vel": [0, 0, 0],
                   "aim": [3.1, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    for _ in range(20):
        o["t"] += 0.1
        o["tick"] += 2
        a = bot.act(o)
        if bot.last_plan.mode != "FIGHT":
            break
        p = o["self"]["pos"]
        o["self"]["pos"] = [p[0] + a["move"][0] * 1.17, p[1] + a["move"][1] * 1.17, p[2]]
        o["events"] = []
    assert math.dist(o["self"]["pos"][:2], (sp.x, sp.y)) < bot.cfg.choke_hold_m
