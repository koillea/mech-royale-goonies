"""Run the bot over the kit's recorded match: valid actions, fast decisions, cover against a laser."""
import time

from mechbot import MechBot


def test_replay_actions_valid_and_fast(hello, observations):
    bot = MechBot(hello)
    worst, modes = 0.0, set()
    for o in observations:
        t = time.perf_counter()
        a = bot.act(o)
        worst = max(worst, time.perf_counter() - t)
        assert a["tick"] == o["tick"]
        assert len(a["move"]) == 2 and (a["move"][0] ** 2 + a["move"][1] ** 2) <= 1.002
        assert len(a["fire"]) == 2 and all(isinstance(x, bool) for x in a["fire"])
        modes.add(bot.last_plan.mode)
    assert worst < 0.040, f"slowest decision {worst * 1000:.1f} ms"
    assert "COVER" in modes   # the recorded match has a laser mech hitting us from 150 m
