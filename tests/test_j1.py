"""J1: go for a supply drop landing within 150 m when nobody engages us; stay in the ring when attacked."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def setup(hello, observations, dist, lands_in):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["drops"] = [{"id": 20001, "pos": [p[0] + dist, p[1], p[2]], "radius": 8, "lands_in": lands_in,
                   "capture_s": 4, "progress": 0, "holder": None}]
    mem = Memory()
    mem.ingest(o)
    return HeuristicPlanner(BotConfig(), hello["config"]), mem, o, p


def test_goes_when_quiet_and_timed(hello, observations):
    pl, mem, o, p = setup(hello, observations, 120, 8.0)
    assert "supply drop" in pl.plan(o, mem).rationale
    pl, mem, o, p = setup(hello, observations, 120, 25.0)        # too early: 10 s walk, 25 s fall
    assert "supply drop" not in pl.plan(o, mem).rationale
    pl, mem, o, p = setup(hello, observations, 170, 0.0)         # too far
    assert "supply drop" not in pl.plan(o, mem).rationale


def test_attacked_outside_skips_inside_stays(hello, observations):
    pl, mem, o, p = setup(hello, observations, 100, 0.0)
    mem.attackers[4] = 199.5
    assert "supply drop" not in pl.plan(o, mem).rationale
    pl, mem, o, p = setup(hello, observations, 3, 0.0)
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 60, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    mem.ingest(o)
    plan = pl.plan(o, mem)
    assert "supply drop" in plan.rationale and plan.target["id"] == 4
