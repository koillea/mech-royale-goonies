"""Cover when shot, fire back from the best angle; never flee from a pusher; the zone comes first."""
import copy
import math

import pytest

from mechbot import BotConfig, MechBot


def setup(hello, observations, dist=90.0):
    """Ground spot with walls nearby, an enemy in the open `dist` away that can see us, and it just shot us."""
    bot = MechBot(hello, BotConfig(use_perches=False))
    wm = bot.wm
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], beams=[],
             projectiles=[], offer=None)
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
                o["self"]["in_zone"] = True
                o["zone"].update(center=[x, y], radius=560, next_center=[x, y], next_radius=380,
                                 shrink_start=o["t"] + 100, shrink_end=o["t"] + 150, dps=20)
                o["mechs"] = [{"id": 9, "kind": "mech", "pos": [ex, ey, eg], "vel": [0, 0, 0],
                               "aim": [math.atan2(y - ey, x - ex), 0], "hp": 1400, "max_hp": 1400,
                               "weapons": ["gun"]}]
                o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun",
                                "bearing": math.atan2(ey - y, ex - x), "by": 9}]
                return bot, o
    pytest.skip("no suitable spot found")


def step(o, bot, shot=False, dt=0.1):
    o["t"] += dt
    o["tick"] += 2
    m = o["mechs"][0] if o["mechs"] else None
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}] if shot else []
    if shot and m is not None:
        p = o["self"]["pos"]
        o["events"][0]["bearing"] = math.atan2(m["pos"][1] - p[1], m["pos"][0] - p[0])
    return bot.act(o)


def walk(o, a):
    p = o["self"]["pos"]
    o["self"]["pos"] = [p[0] + a["move"][0] * 1.17, p[1] + a["move"][1] * 1.17, p[2]]
    o["self"]["vel"] = [a["move"][0] * 11.7, a["move"][1] * 11.7, 0]


def test_shot_in_the_open_takes_cover_hidden_from_the_shooter(hello, observations):
    bot, o = setup(hello, observations)
    a = bot.act(o)
    assert bot.last_plan.mode == "COVER" and a["boost"]
    m = o["mechs"][0]["pos"]
    cx, cy = bot.cover
    assert not bot.wm.los([m[0], m[1], m[2] + 8], [cx, cy, bot.wm.ground(cx, cy) + 4.5])


def test_full_cycle_cover_reload_peek_and_back(hello, observations):
    bot, o = setup(hello, observations)
    o["self"]["weapons"][0]["ammo"] = 4
    a = bot.act(o)
    modes = []
    for _ in range(80):
        walk(o, a)
        a = step(o, bot)
        modes.append(bot.last_plan.mode)
        if bot.last_plan.mode == "COVERED":
            o["self"]["weapons"][0]["ammo"] = 12
        if bot.last_plan.mode == "PEEK":
            break
    assert "COVERED" in modes
    if modes[-1] != "PEEK":
        pytest.skip("this cover has no firing spot toward the shooter")
    for _ in range(4):
        walk(o, a)
        a = step(o, bot)
    a = step(o, bot, shot=True)
    assert bot.last_plan.mode == "COVER"


def test_never_flees_from_a_pusher(hello, observations):
    bot, o = setup(hello, observations, dist=20.0)
    bot.act(o)
    assert bot.last_plan.mode == "FIGHT"


def test_fights_back_when_flanked_in_cover(hello, observations):
    bot, o = setup(hello, observations)
    a = bot.act(o)
    for _ in range(40):
        walk(o, a)
        a = step(o, bot)
        if bot.last_plan.mode == "COVERED":
            break
    assert bot.last_plan.mode == "COVERED"
    # the shooter walks round to a spot that sees us, 50 m away
    p = o["self"]["pos"]
    for k in range(32):
        ang = k * math.pi / 16
        ex, ey = p[0] + math.cos(ang) * 50, p[1] + math.sin(ang) * 50
        if bot.wm.free(ex, ey) and bot.wm.los([ex, ey, bot.wm.ground(ex, ey) + 8], [p[0], p[1], p[2] + 8.7]):
            o["mechs"][0]["pos"] = [ex, ey, bot.wm.ground(ex, ey)]
            break
    else:
        pytest.skip("no flanking spot")
    step(o, bot, shot=True)
    assert bot.last_plan.mode == "FIGHT"


def test_zone_comes_first(hello, observations):
    bot, o = setup(hello, observations)
    o["self"]["in_zone"] = False
    bot.act(o)
    assert bot.last_plan.mode == "ROTATE"


def test_unseen_shooter_still_sends_us_to_cover(hello, observations):
    bot, o = setup(hello, observations)
    o["mechs"] = []                                    # shot by something we cannot see
    bot.act(o)
    assert bot.last_plan.mode == "COVER"
