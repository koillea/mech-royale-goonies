"""O1 aim: lead uses acceleration, gravity and strafe rhythm."""
from mechbot.ballistics import Tracker, intercept, predict


def test_constant_velocity_matches_plain_lead():
    p = intercept([0, 0, 7], [100, 0, 4.5], [0, 10, 0], [0, 0], 252.0, 0.0, 19.5)
    t = ((p[0]) ** 2 + p[1] ** 2 + (p[2] - 7) ** 2) ** 0.5 / 252
    assert abs(p[1] - 10 * t) < 0.05


def test_gravity_brings_a_jumper_down_to_the_floor():
    p = predict([0, 0, 10], [0, 0, 5], [0, 0], 2.0, 19.5, g=22.0, ground=4.5)
    assert p[2] == 4.5


def test_deceleration_is_used_and_speed_capped():
    p = predict([0, 0, 0], [0, 11.7, 0], [0, -29.25], 0.4, 19.5)
    assert abs(p[1] - 11.7 * 0.4 / 2) < 0.01          # stops at the end of 0.4 s
    q = predict([0, 0, 0], [0, 19.5, 0], [0, 50], 1.0, 19.5)
    assert q[1] <= 19.5 + 1e-6


def test_tracker_learns_the_strafe_leg():
    tr = Tracker()
    t = 0.0
    for leg in range(6):
        v = 11.7 if leg % 2 == 0 else -11.7
        for _ in range(10):                            # 1.0 s legs
            tr.update(t, [0, 0, 0], [{"id": 3, "kind": "mech", "pos": [100, 0, 0], "vel": [0, v, 0]}])
            t += 0.1
    assert tr.reversal_due(3, t - 0.5) == 0.0          # half-way through a leg
    assert tr.reversal_due(3, t + 0.3) > 0.5           # past its usual length
