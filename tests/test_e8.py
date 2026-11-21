"""E8: in the opening, go up to 150 m for a laser when nobody is attacking us."""
import copy

from mechbot import MechBot


def setup(hello, observations, dx, t=20.0, attacked=False, mech_near_laser=False):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    o["t"] = t
    p = o["self"]["pos"]
    o["zone"].update(center=[p[0], p[1]], radius=560, next_center=[p[0], p[1]], next_radius=380,
                     shrink_start=t + 60, shrink_end=t + 100, dps=20)
    o["pickups"] = [{"id": 8031, "kind": "laser", "pos": [p[0] + dx, p[1], p[2]]}]
    if mech_near_laser:
        o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + dx + 20, p[1], p[2]], "vel": [0, 0, 0],
                       "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    if attacked:
        o["mechs"] = [{"id": 9, "kind": "mech", "pos": [p[0] - 150, p[1], p[2]], "vel": [0, 0, 0],
                       "aim": [0, 0], "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
        o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 3.1, "by": 9}]
    bot.act(o)
    return bot.last_plan


def test_goes_130m_for_a_laser_in_the_opening(hello, observations):
    pl = setup(hello, observations, 130)
    assert pl.take is not None and pl.take["id"] == 8031


def test_not_after_the_opening_nor_beyond_150m(hello, observations):
    assert setup(hello, observations, 130, t=120).take is None
    assert setup(hello, observations, 170).take is None


def test_not_when_attacked_or_contested(hello, observations):
    assert setup(hello, observations, 130, attacked=True).take is None
    assert setup(hello, observations, 130, mech_near_laser=True).take is None
