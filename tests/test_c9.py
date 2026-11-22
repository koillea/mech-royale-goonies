"""C9: among targets, prefer the one carrying more cubes; an attacker still comes first."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def mech(i, p, dx, cubes, dy=0.0):
    return {"id": i, "kind": "mech", "pos": [p[0] + dx, p[1] + dy, p[2]], "vel": [0, 0, 0], "aim": [0, 0],
            "hp": 1400, "max_hp": 1400, "cubes": cubes, "weapons": ["gun"]}


def test_cube_carrier_first_but_attacker_beats_it(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["mechs"] = [mech(4, p, 50, 0), mech(5, p, 80, 6, dy=10)]
    mem = Memory()
    mem.ingest(o)
    pl = HeuristicPlanner(BotConfig(), hello["config"])
    assert pl.plan(o, mem).target["id"] == 5             # 6 cubes outweigh 30 m
    assert HeuristicPlanner(BotConfig(w_target_cubes=0.0), hello["config"]).plan(o, mem).target["id"] == 4
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    mem.ingest(o)
    assert pl.plan(o, mem).target["id"] == 4             # the one shooting us
