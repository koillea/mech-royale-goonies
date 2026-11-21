"""Avoid fights using intel, keep the ring first, shoot only when necessary, grab a close laser and go back."""
import copy
import math

from mechbot import BotConfig, MechBot


def calm(observations):
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], sounds=[], beams=[],
             projectiles=[], offer=None)
    o["self"]["energy"] = o["self"]["max_energy"] = 100
    return o


def tick(o, k=1):
    o["t"] += 0.1 * k
    o["tick"] += 2 * k


def test_spot_moves_away_from_heard_enemies_but_stays_in_the_ring(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    first = bot.pos_planner.choose(o, None, {})
    heard = [(first.x + 10, first.y, 0.9), (first.x, first.y - 15, 0.8)]   # footsteps and gunfire at the spot
    second = bot.pos_planner.choose(o, None, {}, heard)
    assert math.hypot(second.x - first.x, second.y - first.y) > 30
    assert all(math.hypot(second.x - hx, second.y - hy) > bot.cfg.avoid_near for hx, hy, _ in heard)
    z = o["zone"]
    assert math.hypot(second.x - z["next_center"][0], second.y - z["next_center"][1]) <= z["next_radius"]


def test_enemy_heard_near_us_triggers_a_repick(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    bot.act(o)
    tick(o, 40)                                        # past avoid_respot_s
    before = bot.spot_t
    o["sounds"] = [{"kind": "step", "bearing": 1.0, "dist": "near", "age": 0.0}]
    bot.act(o)
    assert bot.spot_t > before


def test_ring_still_wins_over_avoidance(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    o["self"]["in_zone"] = False
    o["sounds"] = [{"kind": "gun", "bearing": 0.0, "dist": "near", "age": 0.0}]
    bot.act(o)
    assert bot.last_plan.mode == "ROTATE"


def test_does_not_shoot_crates(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    p = o["self"]["pos"]
    o["crates"] = [{"id": 1001, "pos": [p[0] + 15, p[1], p[2]], "hp": 300}]
    a = bot.act(o)
    assert bot.last_plan.target is None and not any(a["fire"])


def test_does_not_shoot_a_passing_mech(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    p = o["self"]["pos"]
    o["mechs"] = [{"id": 4, "kind": "mech", "pos": [p[0] + 70, p[1], p[2]], "vel": [0, 5, 0], "aim": [1.5, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    o["self"]["aim"] = [0.0, 0.0]
    a = bot.act(o)
    assert bot.last_plan.target is None and not any(a["fire"])


def test_grabs_a_close_laser_even_from_the_spot_then_repicks(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    bot.act(o)
    p = o["self"]["pos"]
    o["pickups"] = [{"id": 8011, "kind": "laser", "pos": [p[0] + 25, p[1], p[2]]}]
    tick(o)
    bot.act(o)
    assert bot.last_plan.mode == "LOOT" and bot.last_plan.take["id"] == 8011
    # far laser: ignored
    o["pickups"] = [{"id": 8012, "kind": "laser", "pos": [p[0] + 70, p[1], p[2]]}]
    tick(o)
    bot.act(o)
    assert bot.last_plan.mode != "LOOT" or bot.last_plan.take is None or bot.last_plan.take["id"] != 8012
    # laser with a mech standing near it: ignored
    o["pickups"] = [{"id": 8013, "kind": "laser", "pos": [p[0] + 25, p[1], p[2]]}]
    o["mechs"] = [{"id": 6, "kind": "mech", "pos": [p[0] + 60, p[1], p[2]], "vel": [0, 0, 0], "aim": [0, 0],
                   "hp": 1400, "max_hp": 1400, "weapons": ["gun"]}]
    tick(o)
    bot.act(o)
    assert not (bot.last_plan.mode == "LOOT" and bot.last_plan.take and bot.last_plan.take["id"] == 8013)
    # taking it forces a fresh spot choice straight away
    o["mechs"], o["pickups"] = [], []
    o["events"] = [{"type": "took", "id": 8011, "kind": "laser", "slot": 1}]
    before = bot.spot_t
    tick(o)
    bot.act(o)
    assert bot.spot_t > before


def test_faces_heard_threat_when_idle(hello, observations):
    bot = MechBot(hello)
    o = calm(observations)
    o["sounds"] = [{"kind": "step", "bearing": 2.5, "dist": "near", "age": 0.0}]
    a = bot.act(o)
    assert abs(((a["aim"][0] - 2.5) + math.pi) % (2 * math.pi) - math.pi) < 0.15
