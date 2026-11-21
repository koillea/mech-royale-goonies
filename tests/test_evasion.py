"""The bot must keep moving across the line of fire whenever it shoots or is shot at."""
import copy
import math

from mechbot import MechBot


def _attacked(observations, dist=90.0, weapons=("gun",)):
    o = copy.deepcopy(observations[0])
    me = o["self"]["pos"]
    o.update(pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["self"]["energy"] = 100
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [me[0] + dist, me[1], me[2]], "vel": [0, 0, 0],
                   "aim": [math.pi, 0], "hp": 1400, "max_hp": 1400, "weapons": list(weapons)}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    return o


def test_moves_across_line_of_fire_when_attacked(hello, observations):
    bot = MechBot(hello)
    o = _attacked(observations)
    o["zone"]["next_center"] = o["self"]["pos"][:2]   # already at the hold point: nothing else to move for
    a = bot.act(o)
    mx, my = a["move"]
    assert math.hypot(mx, my) > 0.9                    # not standing still
    assert abs(my) > abs(mx)                           # enemy is due east: the move is mostly north/south
    assert a["boost"]                                  # full energy: boost the strafe


def test_strafe_legs_reverse_at_irregular_intervals(hello, observations):
    bot = MechBot(hello)
    o = _attacked(observations)
    o["zone"]["next_center"] = o["self"]["pos"][:2]
    signs, flips = [], []
    for k in range(120):                               # 12 s of decisions
        o["t"], o["tick"] = 100 + k * 0.1, 2000 + 2 * k
        o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
        a = bot.act(o)
        o["self"]["vel"] = [a["move"][0] * 11.7, a["move"][1] * 11.7, 0]   # the mech moves as commanded
        s = 1 if a["move"][1] > 0 else -1
        if signs and s != signs[-1]:
            flips.append(o["t"])
        signs.append(s)
    legs = [b - a for a, b in zip(flips, flips[1:])]
    assert len(legs) >= 4
    assert min(legs) >= 0.7 and max(legs) <= 2.1
    assert max(legs) - min(legs) > 0.2                 # not a fixed rhythm an enemy could time


def test_backs_off_when_too_close(hello, observations):
    bot = MechBot(hello)
    o = _attacked(observations, dist=20.0)
    o["zone"]["next_center"] = o["self"]["pos"][:2]
    assert bot.act(o)["move"][0] < 0                   # enemy is east: move west


def test_replay_never_idles_while_firing_at_a_mech(hello, observations):
    bot = MechBot(hello)
    idle = 0
    for o in observations:
        a = bot.act(o)
        if any(a["fire"]) and bot.last_plan.target_kind == "mech" and math.hypot(*a["move"]) < 0.5:
            idle += 1
    assert idle == 0
