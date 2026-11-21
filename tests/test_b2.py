"""B2 drone kiting: lead a chasing hunter past a drone."""
import copy
import math

from mechbot import MechBot


def seg(ax, ay, bx, by, q):
    vx, vy = bx - ax, by - ay
    u = max(0.0, min(1.0, ((q[0] - ax) * vx + (q[1] - ay) * vy) / ((vx * vx + vy * vy) or 1e-9)))
    return math.hypot(ax + vx * u - q[0], ay + vy * u - q[1])


def test_kites_when_a_drone_is_placed_for_it(hello, observations):
    kited = 0
    for k in range(0, 200000, 97):
        bot = MechBot(hello)
        wm = bot.wm
        if k >= len(wm.blocked) or kited >= 3:
            break
        if wm.blocked[k]:
            continue
        x, y = wm.center(k)
        hunter, drone = (x - 80, y), (x - 100, y - 40)
        if not (wm.free(*hunter) and wm.free(*drone)):
            continue
        o = copy.deepcopy(observations[0])
        o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
        o["self"]["pos"] = [x, y, wm.ground(x, y)]
        o["zone"].update(center=[x, y], radius=560, next_center=[x, y], next_radius=380,
                         shrink_start=o["t"] + 100, shrink_end=o["t"] + 150, dps=20)
        o["mechs"] = [{"id": 9, "kind": "mech", "pos": [hunter[0], hunter[1], wm.ground(*hunter)],
                       "vel": [0, 0, 0], "aim": [0.0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]},
                      {"id": 105, "kind": "npc", "pos": [drone[0], drone[1], wm.ground(*drone)], "vel": [0, 0, 0],
                       "aim": [0, 0], "hp": 350, "max_hp": 350}]
        o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": math.pi, "by": 9}]
        a = bot.act(o)
        if bot.last_plan.mode != "KITE":
            continue
        kited += 1
        g = bot.last_plan.goal
        assert 48 <= seg(x, y, g[0], g[1], drone) <= 65         # we skim past, outside its 45 m range
        assert seg(hunter[0], hunter[1], g[0], g[1], drone) <= 40   # the chaser's line cuts into it
        assert math.hypot(*a["move"]) > 0.5
    assert kited >= 3


def test_no_drone_no_kite(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [p[0] - 80, p[1], p[2]], "vel": [0, 0, 0], "aim": [0.0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": math.pi, "by": 9}]
    bot.act(o)
    assert bot.last_plan.mode != "KITE"
