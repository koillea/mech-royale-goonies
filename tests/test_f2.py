"""F2: a hit in the back turns us to that attacker at once, unless our target is nearly dead."""
import copy
import math

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def setup(hello, observations, front_hp):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    m = lambda i, dx, hp: {"id": i, "kind": "mech", "pos": [p[0] + dx, p[1], p[2]], "vel": [0, 0, 0],
                           "aim": [0, 0], "hp": hp, "max_hp": 1400, "weapons": ["gun"]}
    o["mechs"] = [m(4, 40, front_hp), m(5, -80, 1400)]              # 4 in front (closer), 5 behind us
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4},
                   {"type": "damaged", "amount": 67, "weapon": "gun", "bearing": math.pi, "by": 5, "rear": True}]
    mem = Memory()
    mem.ingest(o)
    return HeuristicPlanner(BotConfig(), hello["config"]), mem, o


def test_turns_to_the_one_hitting_our_back(hello, observations):
    pl, mem, o = setup(hello, observations, 1400)
    assert pl.plan(o, mem).target["id"] == 5
    off = HeuristicPlanner(BotConfig(face_rear=False), hello["config"])
    assert off.plan(o, mem).target["id"] == 4                       # champion: the closer attacker


def test_keeps_a_nearly_dead_target(hello, observations):
    pl, mem, o = setup(hello, observations, 300)
    assert pl.plan(o, mem).target["id"] == 4


def test_unseen_back_attacker_turns_us_round(hello, observations):
    pl, mem, o = setup(hello, observations, 1400)
    o["mechs"] = [o["mechs"][0]]
    p = pl.plan(o, mem)
    assert p.mode == "ALERT" and abs(p.face_bearing - math.pi) < 1e-6
