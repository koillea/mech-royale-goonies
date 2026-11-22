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
from multiprocessing import Pool, current_process


def _pin():
    """Pin each worker to one core, like the scorer's 1-CPU container (response times are per core)."""
    try:
        ident = current_process()._identity
        cpus = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {cpus[(ident[0] - 1) % len(cpus)] if ident else cpus[0]})
    except (AttributeError, OSError):
        pass       # macOS has no sched_setaffinity: run unpinned

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
    import random
    random.Random(seed * 7919).shuffle(ents)          # identical seating to run.py calibrate
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
        "ms_all": [round(x, 2) for x in ms],
        "max_hp": me.max_hp, "cube_t": list(getattr(me, "cube_t", [])), "rear_hits": getattr(me, "rear_hits", 0),
        "crashes": getattr(me, "crashes", 0),
        "switches": getattr(me, "tgt_switches", 0),
        "heal_n": getattr(me.ctrl, "heal_n", 0),
        "cubes_after_kill": sum(1 for x in getattr(me, "cube_t", []) if any(0 <= x - k <= 20 for k in getattr(me, "kill_t", []))),
        "mode_share": dict(collections.Counter(md for tt, md in me.mode_hist)),
        "hits_taken": sum(1 for x in me.dmg_log if x[1] is not None and x[1] < 100), "plating": sum(1 for _, u in me.upg_t if u == "plating"),
        "laser_by_120": me.laser_t is not None and me.laser_t <= 120.0,
        "first_hit_t": next((x[0] for x in me.dmg_log), None),
        "first_hit_by": next((("drone" if (x[1] or 0) >= 100 else "house" if x[1] is not None else x[2]) for x in me.dmg_log), None),
        "modes_first_60": collections.Counter(md for tt, md in me.mode_hist if tt < 60).most_common(4),
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
    early = [r for r in dead if r["death_t"] < 60]
    if early:
        print(f"\nFIRST-MINUTE DEATHS: {len(early)} of {n} matches")
        for title, key in (("mode at death", lambda r: r["mode"]), ("killed by", lambda r: f"{r['by']}/{r['weapon']}"),
                           ("engagers", lambda r: r["engagers"]), ("where", lambda r: r["where"]),
                           ("first damage from", lambda r: r["first_hit_by"]),
                           ("plan at death", lambda r: (r["rationale"] or "").split(" ")[0:3] and " ".join((r["rationale"] or "").split(" ")[:3]))):
            c = collections.Counter(key(r) for r in early)
            print(f"  {title}: " + ", ".join(f"{k} {v}" for k, v in c.most_common(6)))
        ft = sorted(r["first_hit_t"] for r in early if r["first_hit_t"] is not None)
        if ft:
            print(f"  first damage taken at: median {statistics.median(ft):.0f} s; death at median {statistics.median(r['death_t'] for r in early):.0f} s")
        mc = collections.Counter()
        for r in early:
            for md, k in r["modes_first_60"]:
                mc[md] += k
        print("  decisions in the first minute (these matches): " + ", ".join(f"{k} {v}" for k, v in mc.most_common(6)))


def key_metrics(rs):
    n = len(rs)
    dead = [r for r in rs if r["died"]]
    full15 = [r for r in dead if r["hp15"] is not None]
    return {
        "score": statistics.mean(r["pts"] for r in rs),
        "kills/match": statistics.mean(r["kills"] for r in rs),
        "missed kills/match": sum(len(r["missed"]) for r in rs) / n,
        "deaths outnumbered (2+)": sum(1 for r in dead if (r["engagers"] or 0) >= 2) / n,
        "deaths in COVER": sum(1 for r in dead if r["mode"] == "COVER") / n,
        "dead in first 60 s": sum(1 for r in dead if r["death_t"] < 60) / n,
        "full-to-dead in 15 s": sum(1 for r in full15 if r["hp15"] >= 1300) / max(len(full15), 1),
        "cubes at 20 s": statistics.mean(sum(1 for x in r["cube_t"] if x <= 20) for r in rs),
        "cubes at 60 s": statistics.mean(sum(1 for x in r["cube_t"] if x <= 60) for r in rs),
        "cubes/match": statistics.mean(r["cubes"] for r in rs),
        "cubes within 20 s of a kill": statistics.mean(r["cubes_after_kill"] for r in rs),
        "target switches/match": statistics.mean(r["switches"] for r in rs),
        "heal breaks/match": statistics.mean(r["heal_n"] for r in rs),
        "rear hits taken/match": statistics.mean(r["rear_hits"] for r in rs),
        "mech hits taken/match": statistics.mean(r["hits_taken"] for r in rs),
        "upgrades/match": statistics.mean(len(r["upgrades"]) for r in rs),
        "plating/match": statistics.mean(r["plating"] for r in rs),
        "laser by 2:00": sum(1 for r in rs if r["laser_by_120"]) / n,
        "max armor at end": statistics.mean(r["max_hp"] for r in rs),
        "median death s": statistics.median([r["death_t"] for r in rs if r["died"]] or [0]),
        "max ms": max(r["max_ms"] for r in rs),
        "p99 ms": sorted(x for r in rs for x in r["ms_all"])[int(0.99 * sum(len(r["ms_all"]) for r in rs))],
        "p99.9 ms": sorted(x for r in rs for x in r["ms_all"])[int(0.999 * sum(len(r["ms_all"]) for r in rs))],
        "ticks > 25 ms": sum(1 for r in rs for x in r["ms_all"] if x > 25),
        "crashes (act raised)": sum(r["crashes"] for r in rs),
    }


def compare(results, champion):
    print("\n=== comparison on the same seeds ===")
    names = list(results)
    km = {nm: key_metrics(results[nm]) for nm in names}
    print(f"{'metric':26}" + "".join(f"{nm:>12}" for nm in names))
    for k in km[names[0]]:
        print(f"{k:26}" + "".join(f"{km[nm][k]:12.2f}" for nm in names))
    for nm in names:
        mc = collections.Counter()
        for r in results[nm]:
            mc.update(r["mode_share"])
        tot = sum(mc.values()) or 1
        print(f"time in each mode, {nm}: " + ", ".join(f"{k} {100 * v / tot:.0f}%" for k, v in mc.most_common(9)))
    if len(names) < 2:
        return
    ch = {r["seed"]: r["pts"] for r in results[champion]}
    for nm in names:
        if nm == champion:
            continue
        d = [r["pts"] - ch[r["seed"]] for r in results[nm] if r["seed"] in ch]
        m, se = statistics.mean(d), statistics.stdev(d) / math.sqrt(len(d))
        verdict = "PROMISING (> 2 se)" if m > 2 * se else ("WORSE (< -2 se)" if m < -2 * se else "no clear difference")
        print(f"\n{nm} - {champion}: {m:+.2f} points per match, se {se:.2f} (paired over {len(d)} seeds) -> {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", default="champ", help="comma list; name or name=<gitrev>; the first is the champion")
    ap.add_argument("--matches", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--brief", action="store_true", help="only the comparison table")
    a = ap.parse_args()
    names = [loader.split(v) for v in a.versions.split(",")]
    for nm in names:
        if nm != "example":
            loader._extract(nm, loader.VERSIONS[nm])
    results = {}
    t0 = time.time()
    with Pool(a.workers, initializer=_pin) as pool:
        for nm in names:
            jobs = [(s, nm, dict(loader.VERSIONS)) for s in range(a.seed, a.seed + a.matches)]
            results[nm] = sorted(pool.imap_unordered(one, jobs), key=lambda r: r["seed"])
            if not a.brief:
                report(results[nm], f"{nm} ({time.time() - t0:.0f}s)")
    compare(results, names[0])


if __name__ == "__main__":
    main()
