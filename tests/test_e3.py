"""E3: do not provoke; break off when outnumbered (unless the target is nearly dead)."""
import copy
import math

from mechbot import MechBot


def setup(hello, observations, n_attackers, tgt_hp=1400):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    for k in range(n_attackers):
        a = k * 1.2
        mx, my = p[0] + math.cos(a) * 70, p[1] + math.sin(a) * 70
        o["mechs"].append({"id": 9 + k, "kind": "mech", "pos": [mx, my, p[2]], "vel": [0, 0, 0],
                           "aim": [math.atan2(p[1] - my, p[0] - mx), 0], "hp": tgt_hp, "max_hp": 1400,
                           "weapons": ["gun"]})
        o["events"].append({"type": "damaged", "amount": 45, "weapon": "gun", "bearing": a, "by": 9 + k})
    bot.act(o)
    return bot.last_plan


def test_one_attacker_is_fought(hello, observations):
    pl = setup(hello, observations, 1)
    assert pl.mode == "FIGHT" and not pl.retreat


def test_two_attackers_break_off(hello, observations):
    pl = setup(hello, observations, 2)
    assert pl.mode == "COVER" or pl.retreat


def test_nearly_dead_target_is_still_finished(hello, observations):
    pl = setup(hello, observations, 2, tgt_hp=300)
    assert pl.mode == "FIGHT" and not pl.retreat
