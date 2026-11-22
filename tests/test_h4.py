"""H4: holding a laser, standing, a quiet mech in range: face it and charge the laser in advance."""
import copy

from mechbot import BotConfig, MechBot


def setup(hello, observations, cfg=None):
    bot = MechBot(hello, cfg)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = 200.0
    p = o["self"]["pos"]
    o["self"]["in_zone"] = True
    o["zone"].update(center=list(p[:2]), radius=600, next_center=list(p[:2]), next_radius=400,
                     shrink_start=400.0, shrink_end=450.0)
    o["self"]["weapons"][1] = {"kind": "laser", "cooldown": 0.0, "charge": 0.0,
                               "stats": {"charge": 0.75, "range": 280, "min_charge": 0.15, "hold_s": 2}}
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 200, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    return bot, o


def test_precharges_at_a_quiet_mech_in_range(hello, observations):
    bot, o = setup(hello, observations)
    a = bot.act(o)
    assert bot.last_plan.mode in ("HOLD", "PERCH"), bot.last_plan.rationale     # a quiet mech at 200 m: watched
    assert a["fire"][1] is True and abs(a["aim"][0]) < 0.05                      # charging, facing it (due east)
    assert a["fire"][0] is False


def test_no_precharge_when_off(hello, observations):
    bot, o = setup(hello, observations, BotConfig(laser_precharge=False))
    a = bot.act(o)
    assert a["fire"][1] is False
