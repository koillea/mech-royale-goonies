import copy

from mechbot import BotConfig, HeuristicPlanner
from mechbot.model import Memory, MechBot


def base_obs(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], offer=None)
    return o


def plan(hello, o, mem=None):
    mem = mem or Memory()
    mem.ingest(o)
    return HeuristicPlanner(BotConfig(), hello["config"]).plan(o, mem)


def test_outside_zone_rotates_with_boost(hello, observations):
    o = base_obs(observations)
    o["self"]["in_zone"] = False
    o["self"]["pos"] = [o["zone"]["center"][0] + 600, o["zone"]["center"][1], 0]
    p = plan(hello, o)
    assert p.mode == "ROTATE" and p.boost and p.goal is not None


def test_attacker_becomes_target(hello, observations):
    o = base_obs(observations)
    me = o["self"]["pos"]
    o["mechs"] = [{"id": 9, "kind": "mech", "pos": [me[0] + 150, me[1], me[2]], "vel": [0, 0, 0], "aim": [3.1, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 9}]
    p = plan(hello, o)
    assert p.mode == "FIGHT" and p.target["id"] == 9


def test_far_peaceful_enemy_is_watched_not_shot(hello, observations):
    o = base_obs(observations)
    me = o["self"]["pos"]
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [me[0] + 170, me[1], me[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    p = plan(hello, o)
    assert p.mode == "HOLD" and p.target is None and abs(p.face_bearing) < 0.05


def test_loot_prefers_laser_pickup(hello, observations):
    o = base_obs(observations)
    me = o["self"]["pos"]
    o["pickups"] = [{"id": 8001, "kind": "mortar", "pos": [me[0] + 10, me[1], me[2]]},
                    {"id": 8002, "kind": "laser", "pos": [me[0] + 20, me[1], me[2]]}]
    p = plan(hello, o)
    assert p.mode == "LOOT"
    bot = MechBot(hello)
    ids = [w["id"] for w in bot.planner.wanted_pickups(o)]
    assert 8002 in ids and 8001 in ids


def test_upgrade_pick_prefers_armor(hello, observations):
    o = base_obs(observations)
    o["offer"] = {"id": 1, "expires": 99, "choices": [{"id": "servos", "name": "", "desc": ""},
                                                      {"id": "gun_mag", "name": "", "desc": ""},
                                                      {"id": "armor", "name": "", "desc": ""}]}
    a = MechBot(hello).act(o)
    assert a["pick"] == 2
