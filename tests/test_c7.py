"""C7 faster opener: torso sweep with nothing targeted; remembered items keep the goal while out of view."""
import copy

from mechbot import MechBot


def base(observations, t=5.0):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = t
    o["zone"].update(center=list(o["self"]["pos"][:2]), radius=600, shrink_start=200, shrink_end=260)
    return o


def test_sweeps_the_torso_when_nothing_is_targeted(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    yaws = []
    for _ in range(4):
        a = bot.act(o)
        yaws.append(a["aim"][0])
        o["self"]["aim"] = [a["aim"][0], 0.0]
        o["t"] += 0.1
        o["tick"] += 2
    steps = [((b - a + 3.1416) % 6.2832) - 3.1416 for a, b in zip(yaws, yaws[1:])]
    assert all(abs(s - 0.4) < 0.01 for s in steps)


def test_remembers_a_cube_after_it_leaves_view(hello, observations):
    bot = MechBot(hello)
    o = base(observations)
    p = o["self"]["pos"]
    o["cubes"] = [{"id": 5001, "pos": [p[0] + 80, p[1], p[2]]}]
    bot.act(o)
    assert "OPENER cube" in bot.last_plan.rationale
    o["cubes"] = []
    o["t"] += 0.1
    o["tick"] += 2
    bot.act(o)
    assert "OPENER cube" in bot.last_plan.rationale and abs(bot.last_plan.goal[0] - (p[0] + 80)) < 0.1
    o["t"] += 16.0                                    # forgotten after opener_memory_s
    o["tick"] += 320
    bot.act(o)
    assert "OPENER cube" not in bot.last_plan.rationale
