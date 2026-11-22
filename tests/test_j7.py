"""J7: no kill-cube walk while 2+ mechs engage us; it resumes once only one does."""
import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory


def test_kill_cubes_wait_while_outnumbered(hello, observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["mechs"] = [{"id": i, "kind": "mech", "pos": [p[0] + 60, p[1] + 10 * i, p[2]], "vel": [0, 0, 0],
                   "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]} for i in (4, 5)]
    mem = Memory()
    mem.kill_spot = (p[0] - 40, p[1], 199.0)
    mem.attackers = {4: 199.8, 5: 199.8}
    pl = HeuristicPlanner(BotConfig(), hello["config"])
    assert "kill cubes" not in pl.plan(o, mem).rationale and mem.kill_spot is not None
    assert "kill cubes" in HeuristicPlanner(BotConfig(kill_cubes_solo=False), hello["config"]).plan(o, mem).rationale
    mem.attackers = {4: 199.8}
    assert "kill cubes" in pl.plan(o, mem).rationale
