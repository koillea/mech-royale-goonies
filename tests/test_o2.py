"""O2 full offense: engage, lock on, never cover or retreat, close in, short strafe legs."""
import copy
import math

from mechbot import MechBot


def base(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    return o


def mech(i, p, dx, hp=1400, dy=0.0):
    return {"id": i, "kind": "mech", "pos": [p[0] + dx, p[1] + dy, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
            "hp": hp, "max_hp": 1400, "weapons": ["gun"]}


def test_engages_a_quiet_mech_at_170m(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    o["mechs"] = [mech(4, o["self"]["pos"], 170)]
    bot.act(o)
    assert bot.last_plan.mode == "FIGHT" and bot.last_plan.target["id"] == 4


def test_never_covers_or_retreats_when_losing(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    o["self"]["hp"] = 300
    o["mechs"] = [mech(4, o["self"]["pos"], 120)]
    o["mechs"][0]["weapons"] = ["gun", "laser"]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "laser", "bearing": 0.0, "by": 4}]
    for _ in range(5):
        bot.act(o)
        assert bot.last_plan.mode == "FIGHT" and not bot.last_plan.retreat
        o["t"] += 0.1
        o["tick"] += 2


def test_locks_on_and_switches_only_to_a_nearly_dead_one(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    p = o["self"]["pos"]
    o["mechs"] = [mech(4, p, 60, hp=900)]
    bot.act(o)
    assert bot.last_plan.target["id"] == 4
    o["mechs"].append(mech(5, p, 50, hp=700, dy=10))     # weaker but not nearly dead: keep the lock
    o["t"] += 0.1
    o["tick"] += 2
    bot.act(o)
    assert bot.last_plan.target["id"] == 4
    o["mechs"][1]["hp"] = 300                             # now nearly dead: take it
    o["t"] += 0.1
    o["tick"] += 2
    bot.act(o)
    assert bot.last_plan.target["id"] == 5


def test_order_lowest_hp_then_shooting_us_then_closest(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    p = o["self"]["pos"]
    o["mechs"] = [mech(4, p, 60, hp=1400), mech(5, p, 150, hp=1400, dy=20), mech(6, p, 200, hp=1400, dy=-20)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 6}]
    bot.act(o)
    assert bot.last_plan.target["id"] == 6                # same HP: the one shooting us
    bot = MechBot(hello)
    o["mechs"][1]["hp"] = 800
    bot.act(o)
    assert bot.last_plan.target["id"] == 5                # lowest HP first


def test_closes_in_on_a_target_out_of_range_band(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    o["mechs"] = [mech(4, o["self"]["pos"], 140)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    pushes = []
    for _ in range(20):
        a = bot.act(o)
        pushes.append(a["move"][0])                       # target is due east
        o["t"] += 0.1
        o["tick"] += 2
    assert sum(pushes) / len(pushes) > 0.3
