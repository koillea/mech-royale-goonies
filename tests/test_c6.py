"""C6 kill cubes: after a kill, go to where it died and collect its cubes, still fighting."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def test_goes_to_the_kill_spot_then_its_cubes_and_stops_when_done(hello, observations):
    pl = HeuristicPlanner(BotConfig(after_kill_sweep=False), hello["config"])   # C8 in test_c8.py
    mem = Memory()
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 50, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 40, "max_hp": 1400, "weapons": ["gun"]}]
    mem.ingest(o)
    o["t"] += 0.1
    o["mechs"] = []
    o["events"] = [{"type": "kill", "target": 4}]
    mem.ingest(o)
    pl_ = pl.plan(o, mem)
    assert "kill cubes" in pl_.rationale and abs(pl_.goal[0] - (p[0] + 50)) < 1
    o["events"] = []
    o["cubes"] = [{"id": 5001, "pos": [p[0] + 52, p[1] + 2, p[2]]}]
    o["t"] += 0.1
    assert pl.plan(o, mem).goal == (p[0] + 52, p[1] + 2)
    o["cubes"] = []
    o["self"]["pos"] = [p[0] + 50, p[1], p[2]]
    o["t"] += 0.1
    assert "kill cubes" not in pl.plan(o, mem).rationale and mem.kill_spot is None
