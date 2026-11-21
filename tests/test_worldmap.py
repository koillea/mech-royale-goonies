from mechbot.worldmap import PathSearch


def test_real_positions_are_walkable(wm, observations):
    pts = [o["self"]["pos"] for o in observations] + [m["pos"] for o in observations for m in o["mechs"]]
    blocked = sum(wm.blocked[wm.idx(p[0], p[1])] for p in pts)
    assert blocked / len(pts) < 0.02


def test_ground_matches_recorded_feet(wm, observations):
    grounded = [o["self"]["pos"] for o in observations if o["self"]["grounded"]]
    assert max(abs(wm.ground(p[0], p[1]) - p[2]) for p in grounded) < 0.3


def test_astar_reaches_zone_centre_and_avoids_walls(wm):
    s, g = wm.nearest_free(255, -258), wm.nearest_free(-23, 2)
    ps = PathSearch(wm, s, g)
    for _ in range(50):
        if ps.step(2500):
            break
    assert ps.done and ps.path
    assert all(wm.free(x, y) for x, y in ps.path)
    end = ps.path[-1]
    assert abs(end[0] - wm.center(g)[0]) < 1e-6 and abs(end[1] - wm.center(g)[1]) < 1e-6


def test_los_blocked_by_a_tall_building(wm):
    k = max(range(len(wm.roof)), key=lambda i: wm.roof[i] - wm.gnd[i])
    x, y = wm.center(k)
    z = wm.gnd[k] + 4
    assert not wm.los([x - 40, y, z], [x + 40, y, z]) or not wm.los([x, y - 40, z], [x, y + 40, z])
    assert wm.los([x - 40, y, 300], [x + 40, y, 300])
