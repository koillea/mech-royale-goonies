"""J6: two attackers: the lower-HP one first even if farther; one attacker: unchanged."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def test_lowest_hp_attacker_first(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    m = lambda i, dx, hp: {"id": i, "kind": "mech", "pos": [p[0] + dx, p[1] + i, p[2]], "vel": [0, 0, 0],
                           "aim": [0, 0], "hp": hp, "max_hp": 1960, "weapons": ["gun"]}
    o["mechs"] = [m(4, 40, 1100), m(5, 150, 900)]       # 5 is farther but has less HP left
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": i} for i in (4, 5)]
    mem = Memory()
    mem.ingest(o)
    assert HeuristicPlanner(BotConfig(), hello["config"]).plan(o, mem).target["id"] == 5
    assert HeuristicPlanner(BotConfig(outnumbered_lowest=False), hello["config"]).plan(o, mem).target["id"] == 4
