"""M1: replay the kit's recorded match: valid, fast actions; and a few priority checks."""
import copy
import math
import time

from m1 import M1Bot


def test_replay_valid_and_fast(hello, observations):
    bot = M1Bot(hello)
    worst = 0.0
    modes = set()
    for o in observations:
        t0 = time.perf_counter()
        a = bot.act(o)
        worst = max(worst, time.perf_counter() - t0)
        modes.add(bot.mode)
        assert a["tick"] == o["tick"]
        assert len(a["move"]) == 2 and math.hypot(*a["move"]) <= 1.002
        assert len(a["fire"]) == 2 and all(isinstance(x, bool) for x in a["fire"])
        assert len(a["aim"]) == 2
    assert worst < 0.005, f"slowest decision {worst * 1000:.1f} ms"


def base(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["self"]["in_zone"] = True
    o["zone"].update(next_center=list(o["self"]["pos"][:2]), next_radius=400, shrink_start=o["t"] + 100)
    return o


def test_cube_before_drone_and_fight_beats_farm(hello, observations):
    bot = M1Bot(hello)
    o = base(observations)
    p = o["self"]["pos"]
    o["cubes"] = [{"id": 5001, "pos": [p[0] + 50, p[1], p[2]]}]
    o["mechs"] = [{"id": 105, "kind": "npc", "pos": [p[0] - 80, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 350, "max_hp": 350}]
    bot.act(o)
    assert bot.mode == "CUBE"
    o["mechs"].append({"id": 4, "kind": "mech", "pos": [p[0], p[1] + 60, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                       "hp": 1400, "max_hp": 1400, "weapons": ["gun"]})
    bot.act(o)
    assert bot.mode == "FIGHT" and bot.tgt_id == 4


def test_heal_break_when_two_hit_us_below_half(hello, observations):
    bot = M1Bot(hello)
    o = base(observations)
    p = o["self"]["pos"]
    o["self"]["hp"] = 500
    o["mechs"] = [{"id": i, "kind": "mech", "pos": [p[0] + 60, p[1] + 10 * i, p[2]], "vel": [0, 0, 0],
                   "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]} for i in (4, 5)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": i} for i in (4, 5)]
    a = bot.act(o)
    assert bot.mode == "HEAL" and a["move"][0] < 0          # attackers are east: run west
