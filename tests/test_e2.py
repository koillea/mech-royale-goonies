"""E2: never break off from a nearly dead target; judge losing on HP fractions."""
import copy

from mechbot import MechBot


def fight(hello, observations, my_hp, tgt_hp, tgt_max=1400, weapons=("gun",)):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    o["self"]["hp"] = my_hp
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [p[0] + 70, p[1], p[2]], "vel": [0, 0, 0], "aim": [3.1, 0],
                   "hp": tgt_hp, "max_hp": tgt_max, "weapons": list(weapons)}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    bot.act(o)
    return bot.last_plan


def test_finishes_a_nearly_dead_target_even_when_hurt(hello, observations):
    pl = fight(hello, observations, my_hp=300, tgt_hp=350)          # below 35 %: keep fighting
    assert pl.mode == "FIGHT" and not pl.retreat


def test_still_breaks_off_from_a_healthy_target_when_losing(hello, observations):
    pl = fight(hello, observations, my_hp=300, tgt_hp=1200)
    assert pl.mode in ("COVER", "FIGHT") and (pl.mode == "COVER" or pl.retreat)


def test_losing_uses_fractions(hello, observations):
    # target has 2000 max HP (cubes) and 1500 HP = 75 %; we have 1100 of 1400 = 79 %: not losing
    pl = fight(hello, observations, my_hp=1100, tgt_hp=1500, tgt_max=2000)
    assert pl.mode == "FIGHT"
