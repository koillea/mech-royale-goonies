"""Cover-first combat: being shot sends us to cover, we stay hidden until ready, then peek and duck back."""
import copy
import math

import pytest

from mechbot import BotConfig, MechBot


def setup(hello, observations, dist=90.0):
    """Ground position with a tall building nearby, an enemy out in the open, us just shot by it."""
    bot = MechBot(hello, BotConfig(use_perches=False))
    wm = bot.wm
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    # pick a free ground cell with cover next to it, an open cell `dist` away that sees it
    for k in range(len(wm.blocked)):
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
                return bot, o
    pytest.skip("no suitable spot found")


def step(o, bot, events=None, dt=0.1):
    o["t"] += dt
    o["tick"] += 2
    o["events"] = events or []
    return bot.act(o)


def walk(o, a):
    p = o["self"]["pos"]
    o["self"]["pos"] = [p[0] + a["move"][0] * 1.17, p[1] + a["move"][1] * 1.17, p[2]]
    o["self"]["vel"] = [a["move"][0] * 11.7, a["move"][1] * 11.7, 0]


def test_shot_in_the_open_goes_to_cover_first(hello, observations):
    bot, o = setup(hello, observations)
    a = bot.act(o)
    assert bot.last_plan.mode == "COVER"
    assert a["boost"] and math.hypot(*a["move"]) > 0.9


def test_reaches_cover_hides_reloads_then_peeks_and_returns(hello, observations):
    bot, o = setup(hello, observations)
    modes = []
    o["self"]["weapons"][0]["ammo"] = 5
    for _ in range(80):
        a = step(o, bot)
        modes.append(bot.last_plan.mode)
        walk(o, a)
        if bot.last_plan.mode == "COVERED":
            assert a.get("reload") or o["self"]["weapons"][0]["ammo"] == 12
            o["self"]["weapons"][0]["ammo"] = 12            # the reload finishes while hidden
        if bot.last_plan.mode == "PEEK":
            break
    assert "COVERED" in modes and modes[-1] == "PEEK"
    cover = bot.cover
    for _ in range(6):                                   # step out to the peek point
        walk(o, a)
        a = step(o, bot)
    assert math.dist(o["self"]["pos"][:2], cover) > 2.0
    # shot while peeking: straight back to cover
    a = step(o, bot, events=[{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}])
    assert bot.last_plan.mode == "COVER"
    for _ in range(10):
        walk(o, a)
        a = step(o, bot)
    assert bot.last_plan.mode == "COVERED"


def test_low_hp_stays_hidden(hello, observations):
    bot, o = setup(hello, observations)
    o["self"]["hp"] = 300
    for _ in range(80):
        a = step(o, bot)
        walk(o, a)
    assert bot.last_plan.mode == "COVERED"


def test_shot_outranks_a_mild_zone(hello, observations):
    bot, o = setup(hello, observations)
    o["self"]["in_zone"] = False
    o["zone"]["dps"] = 20
    bot.act(o)
    assert bot.last_plan.mode == "COVER"
    bot2, o2 = setup(hello, observations)
    o2["self"]["in_zone"] = False
    o2["zone"]["dps"] = 100
    bot2.act(o2)
    assert bot2.last_plan.mode == "ROTATE"


def test_goes_far_for_a_laser(hello, observations):
    bot = MechBot(hello, BotConfig(use_perches=False))
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    o["pickups"] = [{"id": 8005, "kind": "laser", "pos": [p[0] + 110, p[1], p[2]]}]
    bot.act(o)
    assert bot.last_plan.mode == "LOOT" and bot.last_plan.take["kind"] == "laser"
