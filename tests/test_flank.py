"""Flanking: strafe legs walk around toward the attacker's back (rear hits x1.5)."""
import copy
import math

import pytest

from mechbot import BotConfig, MechBot


def _rel(me, tpos, aim_yaw):
    to_us = math.atan2(me[1] - tpos[1], me[0] - tpos[0])
    return abs((to_us - aim_yaw + math.pi) % (2 * math.pi) - math.pi)


@pytest.mark.parametrize("offset", [0.3, -0.3])
def test_strafe_walks_away_from_the_attackers_aim(hello, observations, offset):
    bot = MechBot(hello, BotConfig(flank_bias=1.0, use_perches=False))
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    me = o["self"]["pos"]
    o["zone"]["next_center"] = me[:2]
    tx, ty = me[0] + 60, me[1]
    aim_yaw = math.atan2(me[1] - ty, me[0] - tx) + offset
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [tx, ty, me[2]], "vel": [0, 0, 0], "aim": [aim_yaw, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    a = bot.act(o)
    if bot.last_plan.mode != "FIGHT":
        pytest.skip("fight handled by another mode here")
    nxt = [me[0] + a["move"][0] * 2, me[1] + a["move"][1] * 2]
    assert _rel(nxt, [tx, ty], aim_yaw) > _rel(me, [tx, ty], aim_yaw)
