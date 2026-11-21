"""1v1 duels: our bot against ONE expert house bot (the early-game situation: a single hunter).

    python3 sim/duel.py --versions champ=champ-3.77 --duels 200
    python3 sim/duel.py --versions champ=champ-3.77,new=<gitrev> --duels 300 --laser

Nothing else on the map: no drones, crates or floor loot, and the zone never shrinks. The two mechs start
100-200 m apart at random free points; the hunter starts knowing where we are and comes for us. A duel ends
when one dies or after --time seconds (a draw). Same seeds for every version, so differences are paired.

Reported per version: win / loss / draw rate, time to kill (wins and losses), shots, hits and hit rate per
weapon, damage dealt vs taken, our HP left after wins, response time. Less noisy than full matches: one fight,
one outcome.
"""
from __future__ import annotations

import argparse
import copy
import math
import os
import random
import statistics
import sys
import time
from multiprocessing import Pool, current_process

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sim"))
sys.path.insert(0, os.path.join(ROOT, "bot"))

import loader  # noqa: E402
import run  # noqa: E402
from engine import Match  # noqa: E402
from house import house_factory  # noqa: E402


def _pin():
    try:
        ident = current_process()._identity
        cpus = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {cpus[(ident[0] - 1) % len(cpus)] if ident else cpus[0]})
    except (AttributeError, OSError):
        pass


def duel_rules(base):
    r = copy.deepcopy(base)
    r["npc"]["count"] = 0
    r["crates"]["count"] = 0
    r["loot"]["floor_count"] = 0
    for ph in r["zone"]["phases"]:
        ph["hold_s"] = 10000.0
    return r


def one(job):
    seed, name, versions, laser, tmax, level = job
    loader.VERSIONS.update(versions)
    rules = duel_rules(run.rules())
    ents = [(name, loader.factory(name)), (f"house-{level}", house_factory(level))]
    m = Match(run.wm(), rules, ents, seed, os.path.join(ROOT, "arena"))
    us, them = m.mechs[0], m.mechs[1]
    # place them 100-200 m apart on free ground inside the start circle
    rng = random.Random(seed * 31 + 7)
    for _ in range(500):
        d, a = rng.uniform(100, 200), rng.uniform(-math.pi, math.pi)
        x, y = us.pos[0] + math.cos(a) * d, us.pos[1] + math.sin(a) * d
        if m.wm.free(x, y):
            them.pos = [x, y, m.wm.ground(x, y)]
            break
    if laser:
        for mm in (us, them):
            mm.slots[1] = mm._weapon("laser")
    m._squad = {"order": [them.id], "last_known": {us.id: (list(us.pos), 0.0)}}   # the hunter knows where we are
    m.run(max_t=tmax)
    res = "win" if us.alive and not them.alive else ("loss" if not us.alive and them.alive else "draw")
    if not us.alive and not them.alive:
        res = "loss" if us.death_t <= them.death_t else "win"
    ms = us.decide_ms or [0.0]
    return {"seed": seed, "res": res, "t": m.t, "shots": dict(us.shots), "hits": dict(us.hits),
            "dealt": us.dmg_dealt, "taken": us.dmg_taken, "hp_left": max(us.hp, 0.0) / us.max_hp,
            "their_shots": dict(them.shots), "their_hits": dict(them.hits),
            "max_ms": max(ms), "p99_ms": sorted(ms)[int(0.99 * (len(ms) - 1))]}


def report(name, rs):
    n = len(rs)
    w = [r for r in rs if r["res"] == "win"]
    l_ = [r for r in rs if r["res"] == "loss"]
    d = n - len(w) - len(l_)
    print(f"\n=== {name}: {n} duels ===")
    se = math.sqrt(max(len(w) / n * (1 - len(w) / n), 1e-9) / n)
    print(f"win {100 * len(w) / n:.1f}% (se {100 * se:.1f})  loss {100 * len(l_) / n:.1f}%  draw {100 * d / n:.1f}%")
    if w:
        print(f"time to kill (wins): median {statistics.median(r['t'] for r in w):.1f} s;"
              f"  our HP left after a win: median {100 * statistics.median(r['hp_left'] for r in w):.0f}%")
    if l_:
        print(f"time to die (losses): median {statistics.median(r['t'] for r in l_):.1f} s")
    for who, sk, hk in (("we", "shots", "hits"), ("they", "their_shots", "their_hits")):
        parts = []
        for wpn in ("gun", "laser", "lightning", "mortar"):
            sh = sum(r[sk].get(wpn, 0) for r in rs)
            ht = sum(r[hk].get(wpn, 0) for r in rs)
            if sh:
                parts.append(f"{wpn} {ht}/{sh} = {100 * ht / sh:.0f}%")
        print(f"hit rate ({who}): " + (", ".join(parts) or "no shots"))
    print(f"damage dealt / taken per duel: {statistics.mean(r['dealt'] for r in rs):.0f} / "
          f"{statistics.mean(r['taken'] for r in rs):.0f}")
    print(f"response: max {max(r['max_ms'] for r in rs):.1f} ms, p99 (worst duel) {max(r['p99_ms'] for r in rs):.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", default="champ=champ-3.77")
    ap.add_argument("--duels", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--time", type=float, default=150.0)
    ap.add_argument("--level", default="expert")
    ap.add_argument("--laser", action="store_true", help="both start with a laser in slot 1")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    names = [loader.split(v) for v in a.versions.split(",")]
    for nm in names:
        if nm != "example":
            loader._extract(nm, loader.VERSIONS[nm])
    results = {}
    t0 = time.time()
    with Pool(a.workers, initializer=_pin) as pool:
        for nm in names:
            jobs = [(s, nm, dict(loader.VERSIONS), a.laser, a.time, a.level) for s in range(a.seed, a.seed + a.duels)]
            results[nm] = sorted(pool.imap_unordered(one, jobs), key=lambda r: r["seed"])
            report(nm, results[nm])
    if len(names) > 1:
        base = {r["seed"]: r["res"] for r in results[names[0]]}
        for nm in names[1:]:
            better = sum(1 for r in results[nm] if r["res"] == "win" and base[r["seed"]] != "win")
            worse = sum(1 for r in results[nm] if r["res"] != "win" and base[r["seed"]] == "win")
            print(f"\n{nm} vs {names[0]} (same seeds): wins gained {better}, wins lost {worse}"
                  f" -> net {better - worse:+d} of {len(results[nm])} (sign test: clear if |net| > 2*sqrt(gained+lost)"
                  f" = {2 * math.sqrt(max(better + worse, 1)):.1f})")
    print(f"\n({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
