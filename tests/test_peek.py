"""Corner fighting: with a corner within 10 m, alternate a short burst from a peek spot and a duck into cover."""
import copy
import math

import pytest

from mechbot import BotConfig, MechBot


def setup(hello, observations, dist=90.0):
    bot = MechBot(hello, BotConfig(use_perches=False))
    wm = bot.wm
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    for k in range(0, len(wm.blocked), 7):
        if wm.blocked[k] or wm.cover[k] < 6:
            continue
        x, y = wm.center(k)
        for a in range(16):
            ex, ey = x + math.cos(a * math.pi / 8) * dist, y + math.sin(a * math.pi / 8) * dist
            if not wm.free(ex, ey):
                continue
            eg = wm.ground(ex, ey)
            if wm.los([ex, ey, eg + 8], [x, y, wm.gnd[k] + 8.7]):
                o["self"]["pos"] = [x, y, wm.gnd[k]]
                o["self"]["vel"] = [0, 0, 0]
                o["zone"].update(center=[x, y], radius=560, next_center=[x, y], next_radius=380,
                                 shrink_start=o["t"] + 100, shrink_end=o["t"] + 150, dps=20)
                o["mechs"] = [{"id": 9, "kind": "mech", "pos": [ex, ey, eg], "vel": [0, 0, 0],
                               "aim": [math.atan2(y - ey, x - ex), 0], "hp": 1400, "max_hp": 1400,
                               "weapons": ["gun"]}]
                o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun",
                                "bearing": math.atan2(ey - y, ex - x), "by": 9}]
                bot.act(o)
                if bot.pb_cover is not None:
                    return bot, o
    pytest.skip("no corner scenario found")


def step(o, bot, a):
    p = o["self"]["pos"]
    o["self"]["pos"] = [p[0] + a["move"][0] * 1.17, p[1] + a["move"][1] * 1.17, p[2]]
    o["self"]["aim"] = a["aim"]
    o["t"] += 0.1
    o["tick"] += 2
    o["events"] = []
    return bot.act(o)


def test_corner_cycle_peeks_fires_ducks_and_stays_close(hello, observations):
    bot, o = setup(hello, observations)
    start = list(o["self"]["pos"])
    a = bot.act(o)
    modes, fired_in_peek, wm = [], 0, bot.wm
    m = o["mechs"][0]["pos"]
    for _ in range(80):
        a = step(o, bot, a)
        modes.append(bot.last_plan.mode)
        if bot.last_plan.mode == "PEEK" and any(a["fire"]):
            fired_in_peek += 1
        if bot.last_plan.mode == "DUCK" and math.dist(o["self"]["pos"][:2], bot.pb_cover) < 1.0:
            p = o["self"]["pos"]
            assert not wm.los([m[0], m[1], m[2] + 8], [p[0], p[1], p[2] + 4.5])   # hidden while ducked
        assert math.dist(o["self"]["pos"][:2], start[:2]) < 20                    # no long runs
    assert "PEEK" in modes and "DUCK" in modes and fired_in_peek > 0
    switches = sum(1 for x, y in zip(modes, modes[1:]) if x != y)
    assert switches >= 4                                                          # it keeps cycling


def test_no_corner_means_normal_strafing(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    bot.pb_cover = None
    bot._find_corner = lambda *a, **k: (None, None)
    p = o["self"]["pos"]
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [p[0] + 60, p[1], p[2]], "vel": [0, 0, 0], "aim": [math.pi, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    bot.act(o)
    assert bot.last_plan.mode in ("FIGHT", "COVER")
