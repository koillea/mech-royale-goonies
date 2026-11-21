"""Step 2 diagnosis: play one version against the house squad on many seeds and explain where points go.

    python3 sim/diag.py --version champ --matches 200

Per match it records place, time of death, house bots dead at our death, our kills, how every house bot died,
our mode at death, what killed us (weapon, distance), HP 15 s before death, mechs engaging us (hit us in the
last 5 s), roof / cover / open at death, weapons held, upgrades and when, laser time, response times, and
missed kills (house bots we brought below 25 % HP that did not die by our hand). Telemetry is read by the
simulator from the bot's state; the bot code is unchanged.
"""
from __future__ import annotations

import argparse
import collections
import math
import os
import statistics
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sim"))
sys.path.insert(0, os.path.join(ROOT, "bot"))

import loader  # noqa: E402
import run  # noqa: E402
from engine import Match  # noqa: E402
from house import FIELD, house_factory  # noqa: E402


def mode_at(hist, t):
    m = None
    for tt, mode in hist:
        if tt > t:
            break
        m = mode
    return m


def one(job):
    seed, name, versions = job
    loader.VERSIONS.update(versions)
    ents = [(name, loader.factory(name))] + [(f"house-{lv}", house_factory(lv)) for lv in FIELD]
    m = Match(run.wm(), run.rules(), ents, seed, os.path.join(ROOT, "arena"))
    places = m.run()
    me = next(x for x in m.mechs if x.name == name)
    died = me.death_t is not None
    house = [x for x in m.mechs if x.house]
    before = sum(1 for h in house if h.death_t is not None and (not died or h.death_t < me.death_t))
    causes = collections.Counter(h.death_by for h in house if h.death_t is not None and (not died or h.death_t <= me.death_t))
    missed = []
    for h in house:
        if h.min_hp_by_entrant < 0.25 and h.death_by != "entrant":
            missed.append({"mode": mode_at(me.mode_hist, h.entrant_last_hit + 1.5),
                           "after_t": round(h.entrant_last_hit, 1)})
    ms = me.decide_ms or [0.0]
    return {
        "seed": seed, "place": places[me.id], "pts": 16 - places[me.id], "died": died,
        "death_t": me.death_t, "house_dead_before": before, "kills": me.kills, "causes": dict(causes),
        "mode": me.death_mode, "rationale": getattr(me, "death_rationale", None), "by": me.death_by, "weapon": me.death_cause,
        "dist": getattr(me, "death_dist", None), "where": getattr(me, "death_where", None),
        "engagers": getattr(me, "death_engagers", None), "hp15": getattr(me, "hp_15s_before", None),
        "weapons": getattr(me, "death_weapons", [w["kind"] for w in me.slots if w]),
        "upgrades": me.upg_t, "laser_t": me.laser_t, "cubes": me.cubes, "missed": missed,
        "max_ms": max(ms), "avg_ms": sum(ms) / len(ms), "drone_kills": m.telemetry["drone_kills"],
    }


def pct(n, d):
    return f"{100 * n / max(d, 1):.0f}%"


def report(rs, name):
    n = len(rs)
    pts = [r["pts"] for r in rs]
    print(f"\n=== {name}: {n} matches vs the house squad ===")
    print(f"score {statistics.mean(pts):.2f}  sd {statistics.stdev(pts):.2f}  se {statistics.stdev(pts) / math.sqrt(n):.2f}"
          f"  avg place {statistics.mean(r['place'] for r in rs):.2f}  top-3 {pct(sum(r['place'] <= 3 for r in rs), n)}"
          f"  survived to the end {pct(sum(not r['died'] for r in rs), n)}")
    dts = sorted(r["death_t"] for r in rs if r["died"])
    if dts:
        q = lambda f: dts[min(int(f * len(dts)), len(dts) - 1)]
        print(f"death time s: p10 {q(.1):.0f}  median {q(.5):.0f}  p90 {q(.9):.0f}   dead in first 60 s {pct(sum(d < 60 for d in dts), n)}")
    print(f"house bots dead before us: mean {statistics.mean(r['house_dead_before'] for r in rs):.2f}   our kills: mean {statistics.mean(r['kills'] for r in rs):.2f}")
    c = collections.Counter()
    for r in rs:
        c.update(r["causes"])
    tot = sum(c.values()) or 1
    print("how those house bots died: " + ", ".join(f"{k} {v} ({100 * v / tot:.0f}%)" for k, v in c.most_common()))
    dead = [r for r in rs if r["died"]]
    lost = lambda grp: sum(15 - r["pts"] for r in grp)
    total_lost = lost(rs) or 1
    def table(title, key):
        g = collections.defaultdict(list)
        for r in dead:
            g[key(r)].append(r)
        print(f"\n{title} (deaths, share of points lost)")
        for k, grp in sorted(g.items(), key=lambda kv: -lost(kv[1])):
            print(f"  {str(k):28} {len(grp):4d}  {100 * lost(grp) / total_lost:5.1f}% of lost points")
    table("mode at death", lambda r: r["mode"])
    table("killed by", lambda r: f"{r['by']}/{r['weapon']}")
    table("enemies engaging us (hit us in last 5 s)", lambda r: r["engagers"])
    table("where", lambda r: r["where"])
    table("distance to killer", lambda r: None if r["dist"] is None else (f"<{int(r['dist'] // 25 * 25 + 25)} m" if r["dist"] < 150 else "150+ m"))
    hp = [r["hp15"] for r in dead if r["hp15"] is not None]
    if hp:
        print(f"\nHP 15 s before death: median {statistics.median(hp):.0f}  (from full HP to dead in 15 s: {pct(sum(h >= 1300 for h in hp), len(hp))})")
    print(f"laser picked up in {pct(sum(r['laser_t'] is not None for r in rs), n)} of matches; cubes at end/death mean {statistics.mean(r['cubes'] for r in rs):.2f};"
          f" upgrades mean {statistics.mean(len(r['upgrades']) for r in rs):.2f}")
    ups = collections.Counter(u for r in rs for _, u in r["upgrades"])
    if ups:
        print("upgrades taken: " + ", ".join(f"{k} {v}" for k, v in ups.most_common()))
    miss = [x for r in rs for x in r["missed"]]
    mm = collections.Counter(x["mode"] for x in miss)
    print(f"\nmissed kills (house bot below 25 % HP from our hits, not killed by us): {len(miss)} in {n} matches"
          f" ({len(miss) / n:.2f} per match); our mode 1.5 s after the last hit: " + ", ".join(f"{k} {v}" for k, v in mm.most_common()))
    print(f"\nresponse time: avg {statistics.mean(r['avg_ms'] for r in rs):.2f} ms, max {max(r['max_ms'] for r in rs):.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="champ")
    ap.add_argument("--matches", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    name = loader.split(a.version)
    if name != "example":
        loader._extract(name, loader.VERSIONS[name])
    jobs = [(s, name, dict(loader.VERSIONS)) for s in range(a.seed, a.seed + a.matches)]
    t0 = time.time()
    with Pool(a.workers) as pool:
        rs = list(pool.imap_unordered(one, jobs))
    report(rs, f"{name} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
