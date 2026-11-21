"""Scanning: with nothing to face, the torso keeps turning all the way round, also while moving."""
import copy
import math

from mechbot import BotConfig, MechBot


def test_turns_all_the_way_round_while_moving(hello, observations):
    bot = MechBot(hello, BotConfig(use_perches=False))
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["zone"]["next_center"] = [o["self"]["pos"][0] + 300, o["self"]["pos"][1]]   # far: it keeps walking
    o["zone"]["next_radius"] = 100
    seen = set()
    for _ in range(25):
        a = bot.act(o)
        assert math.hypot(*a["move"]) > 0.5
        o["self"]["aim"] = [a["aim"][0], 0.0]          # assume the torso reaches the commanded aim
        for k in range(8):                             # sectors inside the 120 degree view cone
            c = -math.pi + (k + 0.5) * math.pi / 4
            if abs((c - a["aim"][0] + math.pi) % (2 * math.pi) - math.pi) <= math.radians(60):
                seen.add(k)
        o["t"] += 0.1
        o["tick"] += 2
    assert len(seen) == 8                              # every 45 degree sector covered within 2.5 s
