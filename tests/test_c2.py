"""C2 focus fire: keep the lock; switch only to a visible mech under 40 % HP."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def obs0(observations, t=200.0):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = t
    return o


def mech(i, p, dx, hp, dy=0.0):
    return {"id": i, "kind": "mech", "pos": [p[0] + dx, p[1] + dy, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
            "hp": hp, "max_hp": 1400, "weapons": ["gun"]}


def test_lock_holds_and_switches_only_below_40_percent(hello, observations):
    pl = HeuristicPlanner(BotConfig(), hello["config"])
    mem = Memory()
    o = obs0(observations)
    p = o["self"]["pos"]
    o["mechs"] = [mech(4, p, 60, 1400)]
    mem.ingest(o)
    assert pl.plan(o, mem).target["id"] == 4
    o["t"] += 0.1
    o["mechs"].append(mech(5, p, 30, 700, dy=10))        # closer and weaker (50 %): champion would switch
    assert pl.plan(o, mem).target["id"] == 4
    o["t"] += 0.1
    o["mechs"][1]["hp"] = 500                            # 36 %: take it
    assert pl.plan(o, mem).target["id"] == 5
    assert pl.switches == 1


def test_lock_survives_a_short_loss_of_sight(hello, observations):
    pl = HeuristicPlanner(BotConfig(), hello["config"])
    mem = Memory()
    o = obs0(observations)
    p = o["self"]["pos"]
    o["mechs"] = [mech(4, p, 60, 1400)]
    pl.plan(o, mem)
    o["t"] += 1.0
    o["mechs"] = [mech(5, p, 50, 1400, dy=10)]
    pl.plan(o, mem)                                      # 4 out of sight: fight 5 meanwhile
    o["t"] += 0.5
    o["mechs"] = [mech(4, p, 60, 1400), mech(5, p, 30, 1300, dy=10)]
    assert pl.plan(o, mem).target["id"] == 4             # back on the lock, not the closer one
    o["t"] += 0.1
    o["mechs"] = [mech(5, p, 30, 1300, dy=10)]
    o["t"] += 2.5                                        # 4 gone > 2 s: lock released
    pl.plan(o, mem)
    o["t"] += 0.1
    o["mechs"] = [mech(4, p, 60, 1400), mech(5, p, 30, 1300, dy=10)]
    assert pl.plan(o, mem).target["id"] == 5
