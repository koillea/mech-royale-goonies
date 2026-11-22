"""H3: no laser held, one within 60 m, no hits for 2 s: go take it, still fighting."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def setup(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["self"]["weapons"][1] = None
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 70, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [p[0] - 40, p[1], p[2]]}]
    mem = Memory()
    mem.ingest(o)
    return HeuristicPlanner(BotConfig(), hello["config"]), mem, o, p


def test_takes_a_laser_in_a_lull_while_targeting(hello, observations):
    pl, mem, o, p = setup(hello, observations)
    mem.took_damage_t = 197.0
    plan = pl.plan(o, mem)
    assert "laser in a lull" in plan.rationale and plan.goal == (p[0] - 40, p[1]) and plan.target["id"] == 4


def test_not_while_being_hit(hello, observations):
    pl, mem, o, p = setup(hello, observations)
    mem.took_damage_t = 199.0
    assert "lull" not in pl.plan(o, mem).rationale


def test_h5_reaches_a_laser_at_85m(hello, observations):
    pl, mem, o, p = setup(hello, observations)
    o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [p[0] - 85, p[1], p[2]]}]
    mem.took_damage_t = 197.0
    assert "laser in a lull" in pl.plan(o, mem).rationale
