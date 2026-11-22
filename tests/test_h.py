"""H1/H2: upgrade choice order."""
EXPECT = ["plating", "laser_charge", "plating"]   # H2: laser first when offered, else plating, armour
from mechbot import BotConfig, MechBot


def pick(hello, ids, cfg=None):
    bot = MechBot(hello, cfg)
    act = {}
    bot._offer({"offer": {"id": 1, "expires": 5, "choices": [{"id": i} for i in ids]}}, act)
    return ids[act["pick"]]


def test_upgrade_order(hello):
    assert pick(hello, ["plating", "armor", "gun_rate"]) == EXPECT[0]
    assert pick(hello, ["plating", "laser_charge", "gun_damage"]) == EXPECT[1]
    assert pick(hello, ["servos", "armor", "plating"]) == EXPECT[2]
