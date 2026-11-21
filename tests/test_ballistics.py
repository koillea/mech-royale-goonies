import math

from mechbot.ballistics import lead, mortar_pitch, mortar_time, wrap


def test_lead_meets_moving_target():
    src, tpos, tvel, sp = [0, 0, 7], [120, 30, 4.5], [0, 11.7, 0], 252.0
    p = lead(src, tpos, tvel, sp)
    t = math.dist(src, p) / sp
    hit = [tpos[i] + tvel[i] * t for i in range(3)]
    assert math.dist(hit, p) < 0.05


def test_mortar_pitch_lands_on_target():
    d, dz, sp, g = 150.0, -3.0, 72.0, 22.0
    p = mortar_pitch(d, dz, sp, g)
    t = mortar_time(d, p, sp)
    z = sp * math.sin(p) * t - 0.5 * g * t * t
    assert abs(z - dz) < 0.05
    assert mortar_pitch(400.0, 0.0, sp, g) is None   # beyond v^2/g


def test_wrap():
    assert abs(wrap(3 * math.pi) - math.pi) < 1e-9 or abs(wrap(3 * math.pi) + math.pi) < 1e-9
    assert abs(wrap(0.5)) - 0.5 < 1e-12
