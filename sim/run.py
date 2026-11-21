"""Run simulated matches and compare bot versions.

    python3 sim/run.py calibrate --matches 24            # each version alone vs 15 house bots (the scorer's format)
    python3 sim/run.py lobby --versions v1,v3,v5,try-b --matches 12   # versions against each other (+ house fill)
    python3 sim/run.py one --versions v3 --seed 1 --log   # a single match, verbose

Same seeds for every version (common random numbers), so differences are not just luck of the spawn.
Score = mean of 16 - place, as on the board. Workers run matches in parallel.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import statistics
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sim"))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from engine import Match  # noqa: E402
from house import FIELD, house_factory  # noqa: E402
import loader  # noqa: E402

_WM = None
_RULES = None


def rules():
    global _RULES
    if _RULES is None:
        with gzip.open(os.path.join(ROOT, "kit", "check", "stream.jsonl.gz"), "rt") as f:
            _RULES = json.loads(f.readline())["config"]
    return _RULES


def wm():
    global _WM
    if _WM is None:
        from mechbot.worldmap import WorldMap
        _WM = WorldMap(os.path.join(ROOT, "arena"))
    return _WM


def play(job):
    """job = (seed, [entrant names], house levels to fill) -> per-entrant (name, points, decide stats)."""
    seed, names, fill = job
    ents = [(n, loader.factory(n)) for n in names] + [(f"house-{lv}", house_factory(lv)) for lv in fill]
    # shuffle seats deterministically by seed so slot order does not matter
    import random
    rnd = random.Random(seed * 7919)
    rnd.shuffle(ents)
    t0 = time.time()
    m = Match(wm(), rules(), ents, seed, os.path.join(ROOT, "arena"))
    places = m.run()
    out = []
    for mech in m.mechs:
        if mech.name.startswith("house-"):
            continue
        ms = sorted(mech.decide_ms) or [0.0]
        out.append((mech.name, 16 - places[mech.id], ms[-1], ms[int(len(ms) * 0.99)], mech.kills,
                    round(m.t, 1)))
    return out, time.time() - t0


def summarize(rows, title):
    by = {}
    for name, pts, mx, p99, kills, t in rows:
        by.setdefault(name, []).append((pts, mx, kills))
    print(f"\n{title}")
    print(f"{'version':10} {'n':>4} {'mean pts':>9} {'± se':>6} {'real':>6} {'kills':>6} {'max ms':>7}")
    for name in sorted(by, key=lambda k: -statistics.mean(p for p, _, _ in by[k])):
        pts = [p for p, _, _ in by[name]]
        se = statistics.stdev(pts) / math.sqrt(len(pts)) if len(pts) > 1 else 0.0
        real = loader.REAL_SCORES.get(name)
        print(f"{name:10} {len(pts):4d} {statistics.mean(pts):9.2f} {se:6.2f} {real if real is not None else '':>6} "
              f"{statistics.mean(k for _, _, k in by[name]):6.2f} {max(x for _, x, _ in by[name]):7.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["calibrate", "lobby", "one"])
    ap.add_argument("--versions", default="example,v1,v3,v4,abc,v5")
    ap.add_argument("--matches", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    names = a.versions.split(",")
    for n in names:                       # extract trees once, before forking workers
        if n != "example":
            loader._extract(n, loader.VERSIONS[n])
    jobs = []
    if a.mode == "one":
        jobs = [(a.seed, names, FIELD[: 16 - len(names)])]
    elif a.mode == "calibrate":
        for s in range(a.seed, a.seed + a.matches):
            for n in names:
                jobs.append((s, [n], FIELD))
    else:
        per = max(1, 16 // len(names))
        for s in range(a.seed, a.seed + a.matches):
            ents = [n for n in names for _ in range(per)][:16]
            jobs.append((s, ents, FIELD[: 16 - len(ents)]))
    t0 = time.time()
    rows = []
    with Pool(a.workers) as pool:
        for i, (out, dt) in enumerate(pool.imap_unordered(play, jobs)):
            rows += out
            if a.log or (i + 1) % max(1, len(jobs) // 10) == 0:
                print(f"  {i + 1}/{len(jobs)} matches ({dt:.0f}s last, {time.time() - t0:.0f}s total)", flush=True)
    summarize(rows, f"{a.mode}: {len(jobs)} matches, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
