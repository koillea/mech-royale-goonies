"""E9: below 70 % and not being hit, start no new fights until back above 95 %; still fire back."""
import copy

from mechbot import MechBot


def setup(observations, hp, attacked=False):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    p = o["self"]["pos"]
    o["self"]["hp"] = hp
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 60, p[1], p[2]], "vel": [0, 0, 0], "aim": [3.1, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    if attacked:
        o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 4}]
    return o


def test_hurt_and_not_hit_does_not_start_a_fight(hello, observations):
    bot = MechBot(hello)
    bot.act(setup(observations, hp=800))            # 57 %: within 90 m, but we are healing
    assert bot.last_plan.target is None


def test_hurt_but_attacked_fires_back(hello, observations):
    bot = MechBot(hello)
    bot.act(setup(observations, hp=800, attacked=True))
    assert bot.last_plan.target is not None and bot.last_plan.target["id"] == 4


def test_healthy_fights_as_before_and_healing_ends_at_95(hello, observations):
    bot = MechBot(hello)
    bot.act(setup(observations, hp=1400))
    assert bot.last_plan.target is not None
    bot2 = MechBot(hello)
    o = setup(observations, hp=800)
    bot2.act(o)
    assert bot2.planner.healing
    o["self"]["hp"], o["t"], o["tick"] = 1340, o["t"] + 10, o["tick"] + 200   # 96 %
    bot2.act(o)
    assert not bot2.planner.healing and bot2.last_plan.target is not None
