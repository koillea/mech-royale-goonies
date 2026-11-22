"""J4: last 60 s with <= 4 alive: no new fights; still answer attackers."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def test_no_new_fights_late_but_answers_attacks(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"], o["alive"] = 430.0, 3
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=200, next_center=list(p[:2]), next_radius=150,
                     shrink_start=600.0, shrink_end=650.0)
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 50, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    mem = Memory()
    mem.ingest(o)
    assert HeuristicPlanner(BotConfig(), hello["config"]).plan(o, mem).target is None
    assert HeuristicPlanner(BotConfig(endgame_hp=False), hello["config"]).plan(o, mem).target["id"] == 4
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    mem.ingest(o)
    assert HeuristicPlanner(BotConfig(), hello["config"]).plan(o, mem).target["id"] == 4
