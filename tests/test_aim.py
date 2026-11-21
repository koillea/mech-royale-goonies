"""Aim: prediction for steady movers, strafers and jumpers, wall clamping, pre-aim, rear-arc preference."""
import copy
import math

import pytest

from mechbot import BotConfig, MechBot
from mechbot.aim import TargetTracker, rear_exposure
from mechbot.ballistics import lead


def feed(tr, tid, samples):
    for t, pos, vel in samples:
        tr.update({"t": t, "mechs": [{"id": tid, "kind": "mech", "pos": pos, "vel": vel}]})


def test_steady_mover_matches_closed_form_lead():
    tr = TargetTracker(None)
    feed(tr, 5, [(t * 0.1, [100 + 0, 11.7 * t * 0.1, 0], [0, 11.7, 0]) for t in range(10)])
    last = tr.last(5)
    muzzle = [0, 0, 7]
    p, tt = tr.intercept(5, muzzle, 252.0, 4.5, latency=0.0)
    q = lead(muzzle, [last[1][0], last[1][1], 4.5], [0, 11.7, 0], 252.0)
    assert math.dist(p, q) < 0.05


def test_strafer_aims_at_jitter_centre():
    tr = TargetTracker(None)
    samples, y, v = [], 0.0, 11.7
    for k in range(20):                     # legs reverse every 0.5 s, no net drift
        if k and k % 5 == 0:
            v = -v
        samples.append((k * 0.1, [100, y, 0], [0, v, 0]))
        y += v * 0.1
    feed(tr, 7, samples)
    assert tr.reversals(7, [0, 0, 0]) >= 2
    p = tr.predict(7, 0.4, [0, 0, 0])
    naive = samples[-1][1][1] + samples[-1][2][1] * 0.4
    assert abs(p[1] - 0.0) < abs(naive - 0.0)           # closer to the centre than chasing the current leg


def test_jumper_falls_but_not_through_ground(wm):
    tr = TargetTracker(wm)
    x, y = wm.center(wm.nearest_free(0, 0))
    g = wm.ground(x, y)
    feed(tr, 3, [(0.0, [x, y, g + 6], [0, 0, 2.0])])
    p = tr.predict(3, 0.3, [x + 100, y, g])
    assert p[2] < g + 6 + 2.0 * 0.3                     # gravity pulls it down
    assert tr.predict(3, 3.0, [x + 100, y, g])[2] >= g - 0.01


def test_prediction_does_not_go_through_walls(wm):
    tr = TargetTracker(wm)
    # a free cell next to a blocked one, moving straight into the block
    for k in range(len(wm.blocked)):
        if not wm.blocked[k] and k + 1 < len(wm.blocked) and wm.blocked[k + 1] and wm.blocked[k + 2]:
            break
    x, y = wm.center(k)
    feed(tr, 4, [(0.0, [x, y, wm.ground(x, y)], [11.7, 0, 0])])
    p = tr.predict(4, 1.0, [x - 100, y, 0])
    assert wm.free(p[0], p[1])


def test_rear_exposure():
    tgt = {"pos": [0, 0, 0], "aim": [0.0, 0.0]}      # facing east
    assert rear_exposure(tgt, [-50, 0, 0]) > 0       # we are behind it
    assert rear_exposure(tgt, [50, 0, 0]) < 0


def calm(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    return o


def test_preaims_at_a_watched_mech(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    me = o["self"]["pos"]
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [me[0], me[1] + 170, me[2]], "vel": [0, 0, 0],
                   "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    a = bot.act(o)
    assert bot.last_plan.target is None                # too far to fight...
    assert abs(a["aim"][0] - math.pi / 2) < 0.02       # ...but the torso is already on it


def test_preaims_where_a_hidden_attacker_was_heading(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    me = o["self"]["pos"]
    o["mechs"] = [{"id": 6, "kind": "mech", "pos": [me[0] + 100, me[1], me[2]], "vel": [0, 10, 0],
                   "aim": [math.pi, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 6}]
    bot.act(o)
    o["mechs"], o["events"] = [], []
    o["t"] += 1.0
    o["tick"] += 20
    a = bot.act(o)
    want = math.atan2(10 * 1.0, 100)                  # it was moving north at 10 m/s: 10 m further along
    assert abs(a["aim"][0] - want) < 0.05


def test_prefers_target_facing_away(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    me = o["self"]["pos"]
    o["mechs"] = [
        {"id": 1, "kind": "mech", "pos": [me[0] + 60, me[1], me[2]], "vel": [0, 0, 0], "aim": [math.pi, 0],
         "hp": 1400, "max_hp": 1400, "weapons": ["gun"]},                      # facing us
        {"id": 2, "kind": "mech", "pos": [me[0] - 65, me[1], me[2]], "vel": [0, 0, 0], "aim": [math.pi, 0],
         "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]                      # back turned to us
    bot.act(o)
    assert bot.last_plan.target["id"] == 2


def _rel(me, tpos, aim_yaw):
    to_us = math.atan2(me[1] - tpos[1], me[0] - tpos[0])
    return abs((to_us - aim_yaw + math.pi) % (2 * math.pi) - math.pi)


@pytest.mark.parametrize("offset", [0.3, -0.3])
def test_strafe_legs_walk_around_to_the_back(hello, observations, offset):
    bot = MechBot(hello, BotConfig(flank_bias=1.0))
    o = calm(observations)
    me = o["self"]["pos"]
    o["zone"]["next_center"] = me[:2]
    tx, ty = me[0] + 60, me[1]
    aim_yaw = math.atan2(me[1] - ty, me[0] - tx) + offset          # aiming just beside us
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [tx, ty, me[2]], "vel": [0, 0, 0], "aim": [aim_yaw, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    a = bot.act(o)
    nxt = [me[0] + a["move"][0] * 2, me[1] + a["move"][1] * 2]
    assert _rel(nxt, [tx, ty], aim_yaw) > _rel(me, [tx, ty], aim_yaw)   # moving away from its line of fire
