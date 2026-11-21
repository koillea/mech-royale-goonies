"""Run simulated matches and compare bot versions.

    python3 sim/run.py calibrate --matches 200 --versions champ,try=<gitrev>   # challenger vs champion, same seeds
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
    """job = (seed, [entrant names], house levels to fill) -> per-entrant result rows."""
    seed, names, fill, versions = job
    loader.VERSIONS.update(versions)
    ents = [(n, loader.factory(n)) for n in names] + [(f"house-{lv}", house_factory(lv)) for lv in fill]
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
        ms = mech.decide_ms or [0.0]
        out.append({"name": mech.name, "seed": seed, "pts": 16 - places[mech.id], "place": places[mech.id],
                    "death_t": mech.death_t, "zone_death": mech.death_cause == "zone",
                    "max_ms": max(ms), "avg_ms": sum(ms) / len(ms), "kills": mech.kills, "cubes": mech.cubes})
    return out, time.time() - t0


def summarize(rows, title, champion=None):
    """The experiment metrics: mean +- spread of placement points, average place, % dead in the first minute,
    % top-3, deaths outside the zone, response time; and, against `champion`, the paired difference on the
    same seeds with its standard error (the only number that decides KEEP / REVERT)."""
    by = {}
    for r in rows:
        by.setdefault(r["name"], []).append(r)
    print(f"\n{title}")
    hdr = f"{'version':10} {'n':>4} {'mean pts':>8} {'sd':>5} {'se':>5} {'avg place':>9} {'die<60s':>7} {'top3':>5} {'zone dth':>8} {'avg ms':>6} {'max ms':>6} {'real':>5}"
    print(hdr)
    for name in sorted(by, key=lambda k: -statistics.mean(r["pts"] for r in by[k])):
        rs = by[name]
        pts = [r["pts"] for r in rs]
        sd = statistics.stdev(pts) if len(pts) > 1 else 0.0
        n = len(pts)
        real = loader.REAL_SCORES.get(name, "")
        print(f"{name:10} {n:4d} {statistics.mean(pts):8.2f} {sd:5.2f} {sd / math.sqrt(n):5.2f} "
              f"{statistics.mean(r['place'] for r in rs):9.2f} "
              f"{100 * sum(1 for r in rs if r['death_t'] is not None and r['death_t'] < 60) / n:6.0f}% "
              f"{100 * sum(1 for r in rs if r['place'] <= 3) / n:4.0f}% "
              f"{100 * sum(1 for r in rs if r['zone_death']) / n:7.0f}% "
              f"{statistics.mean(r['avg_ms'] for r in rs):6.2f} {max(r['max_ms'] for r in rs):6.1f} {real!s:>5}")
    if champion and champion in by:
        ch = {r["seed"]: r["pts"] for r in by[champion]}
        for name in by:
            if name == champion:
                continue
            d = [r["pts"] - ch[r["seed"]] for r in by[name] if r["seed"] in ch]
            if len(d) > 1:
                m, se = statistics.mean(d), statistics.stdev(d) / math.sqrt(len(d))
                verdict = "BETTER" if m > 2 * se else ("WORSE" if m < -2 * se else "no clear difference")
                print(f"  {name} vs {champion} (paired, same seeds): {m:+.2f} +- {se:.2f} (2 se = {2 * se:.2f}) -> {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["calibrate", "lobby", "one"])
    ap.add_argument("--versions", default="example,v1,v3,v4,abc,v5")
    ap.add_argument("--matches", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--champion", default="champ", help="version the others are compared to, seed by seed")
    a = ap.parse_args()
    names = [loader.split(v) for v in a.versions.split(",")]
    for n in names:                       # extract trees once, before forking workers
        if n != "example":
            loader._extract(n, loader.VERSIONS[n])
    vers = dict(loader.VERSIONS)
    jobs = []
    if a.mode == "one":
        jobs = [(a.seed, names, FIELD[: 16 - len(names)], vers)]
    elif a.mode == "calibrate":
        for s in range(a.seed, a.seed + a.matches):
            for n in names:
                jobs.append((s, [n], FIELD, vers))
    else:
        per = max(1, 16 // len(names))
        for s in range(a.seed, a.seed + a.matches):
            ents = [n for n in names for _ in range(per)][:16]
            jobs.append((s, ents, FIELD[: 16 - len(ents)], vers))
    t0 = time.time()
    rows = []
    with Pool(a.workers) as pool:
        for i, (out, dt) in enumerate(pool.imap_unordered(play, jobs)):
            rows += out
            if a.log or (i + 1) % max(1, len(jobs) // 10) == 0:
                print(f"  {i + 1}/{len(jobs)} matches ({dt:.0f}s last, {time.time() - t0:.0f}s total)", flush=True)
    summarize(rows, f"{a.mode}: {len(jobs)} matches, {time.time() - t0:.0f}s", a.champion)


if __name__ == "__main__":
    main()
