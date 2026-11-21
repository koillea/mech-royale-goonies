"""Intel: enemy estimates from beams, sounds, damage, bullets; merging, decay; pre-aim at what we heard."""
import copy
import math

from mechbot import BotConfig, MechBot
from mechbot.intel import Intel


def obs_at(t=10.0, pos=(0.0, 0.0, 0.0), **kw):
    o = {"t": t, "self": {"pos": list(pos)}, "mechs": [], "beams": [], "events": [], "projectiles": [], "sounds": []}
    o.update(kw)
    return o


def intel(hello):
    return Intel(BotConfig(), hello["config"])


def test_beam_gives_exact_shooter_position(hello):
    it = intel(hello)
    it.update(obs_at(beams=[{"by": 5, "kind": "laser", "path": [[100, 50, 7.0], [0, 0, 4]], "age": 0.0}]))
    th = it.threats["m5"]
    assert th.src == "beam" and math.dist(th.pos, [100, 50, 0]) < 0.01 and "laser" in th.weapons


def test_footsteps_place_someone_close_on_that_bearing(hello):
    it = intel(hello)
    it.update(obs_at(sounds=[{"kind": "step", "bearing": math.pi / 2, "dist": "near", "age": 0.0}]))
    (th,) = it.threats.values()
    assert th.mech_id is None and 15 < th.pos[1] < 40 and abs(th.pos[0]) < 1


def test_unseen_damage_uses_matching_gunfire_distance(hello):
    it = intel(hello)
    it.update(obs_at(events=[{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 3}],
                     sounds=[{"kind": "gun", "bearing": 0.05, "dist": "mid", "age": 0.0}]))
    th = it.threats["m3"]
    assert abs(th.pos[0] - 110) < 1 and th.hostile_t == 10.0


def test_incoming_bullet_points_back_at_the_shooter(hello):
    it = intel(hello)
    it.update(obs_at(projectiles=[{"id": 1, "kind": "gun", "pos": [-40, 0, 7], "vel": [252, 0, 0]}]))
    (th,) = it.threats.values()
    assert th.pos[0] < -40                                  # behind the bullet, i.e. to the west


def test_seen_mech_absorbs_the_sound_and_old_estimates_fade(hello):
    it = intel(hello)
    it.update(obs_at(sounds=[{"kind": "jet", "bearing": 0.0, "dist": "mid", "age": 0.0}]))
    assert any(th.mech_id is None for th in it.threats.values())
    it.update(obs_at(t=10.5, mechs=[{"id": 8, "kind": "mech", "pos": [70, 3, 0], "vel": [0, 0, 0]}]))
    assert all(th.mech_id is not None for th in it.threats.values())
    it.update(obs_at(t=40.0))
    assert not it.threats


def test_preaims_at_footsteps_round_the_corner(hello, observations):
    bot = MechBot(hello)
    o = copy.deepcopy(observations[0])
    o.update(mechs=[], events=[], pickups=[], cubes=[], crates=[], drops=[], beams=[], projectiles=[], offer=None)
    o["sounds"] = [{"kind": "step", "bearing": -2.0, "dist": "near", "age": 0.0},
                   {"kind": "boost", "bearing": -2.05, "dist": "near", "age": 0.0}]
    a = bot.act(o)
    assert abs(((a["aim"][0] + 2.0) + math.pi) % (2 * math.pi) - math.pi) < 0.1
