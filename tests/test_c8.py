"""C8: after the kill's own cubes, sweep up other visible cubes within 60 m unless being hit."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def setup(hello, observations):
    pl = HeuristicPlanner(BotConfig(), hello["config"])
    mem = Memory()
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = list(o["self"]["pos"])
    o["self"]["in_zone"] = True
    o["zone"].update(center=p[:2], radius=600, next_center=p[:2], next_radius=400, shrink_start=400.0, shrink_end=450.0)
    mem.kill_spot = (p[0], p[1], 199.0)                  # we stand on the kill spot, its cubes are taken
    o["cubes"] = [{"id": 5009, "pos": [p[0] + 40, p[1] + 5, p[2]]}]
    return pl, mem, o, p


def test_collects_another_cube_within_60m(hello, observations):
    pl, mem, o, p = setup(hello, observations)
    plan = pl.plan(o, mem)
    assert "after-kill cube" in plan.rationale and plan.goal == (p[0] + 40, p[1] + 5)


def test_not_while_being_hit(hello, observations):
    pl, mem, o, p = setup(hello, observations)
    mem.took_damage_t = 199.5
    assert "after-kill" not in pl.plan(o, mem).rationale


def test_keeps_going_to_the_extra_cube_after_leaving_the_spot(hello, observations):
    pl, mem, o, p = setup(hello, observations)
    pl.plan(o, mem)
    o["self"]["pos"] = [p[0] + 20, p[1] + 2, p[2]]       # half-way there, 20 m from the kill spot
    o["t"] += 1.0
    plan = pl.plan(o, mem)
    assert "after-kill cube" in plan.rationale and plan.goal == (p[0] + 40, p[1] + 5)
