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


def duel_rules(base, loot=False):
    r = copy.deepcopy(base)
    r["npc"]["count"] = 0
    if not loot:
        r["crates"]["count"] = 0
        r["loot"]["floor_count"] = 0
    for ph in r["zone"]["phases"]:
        ph["hold_s"] = 10000.0
    return r


def one(job):
    seed, name, versions, laser, tmax, level, vs, loot = job
    loader.VERSIONS.update(versions)
    rules = duel_rules(run.rules(), loot)
    ents = [(name, loader.factory(name))] + [(f"house-{level}", house_factory(level)) for _ in range(vs)]
    m = Match(run.wm(), rules, ents, seed, os.path.join(ROOT, "arena"))
    us, foes = m.mechs[0], m.mechs[1:]
    # place each foe 100-200 m from us on free ground
    rng = random.Random(seed * 31 + 7)
    for them in foes:
        for _ in range(500):
            d, a = rng.uniform(100, 200), rng.uniform(-math.pi, math.pi)
            x, y = us.pos[0] + math.cos(a) * d, us.pos[1] + math.sin(a) * d
            if m.wm.free(x, y):
                them.pos = [x, y, m.wm.ground(x, y)]
                break
    if laser:
        for mm in m.mechs:
            mm.slots[1] = mm._weapon("laser")
    m._squad = {"order": [f.id for f in foes], "last_known": {us.id: (list(us.pos), 0.0)}}
    if vs > 1:                       # 1vN: every foe hunts us (the late-game / outnumbered situation)
        import house
        house.ALL_HUNT_T = 0.0
    m.run(max_t=tmax)
    kills = sum(1 for f in foes if not f.alive)
    if vs == 1:
        them = foes[0]
        res = "win" if us.alive and not them.alive else ("loss" if not us.alive and them.alive else "draw")
        if not us.alive and not them.alive:
            res = "loss" if us.death_t <= them.death_t else "win"
    else:
        res = "win" if kills == vs and us.alive else ("loss" if not us.alive else "draw")
    ms = us.decide_ms or [0.0]
    sh = lambda attr: {k: sum(getattr(f, attr).get(k, 0) for f in foes) for k in ("gun", "laser", "lightning", "mortar")}
    return {"seed": seed, "res": res, "t": m.t, "kills": kills,
            "survive_t": us.death_t if us.death_t is not None else m.t,
            "shots": dict(us.shots), "hits": dict(us.hits),
            "dealt": us.dmg_dealt, "taken": us.dmg_taken, "hp_left": max(us.hp, 0.0) / us.max_hp,
            "their_shots": sh("shots"), "their_hits": sh("hits"),
            "their_shot_d": [d for f in foes for d in f.shot_d], "their_hit_d": [d for f in foes for d in f.hit_d],
            "our_shot_d": us.shot_d, "our_hit_d": us.hit_d,
            "our_laser_t": us.laser_t if not laser else 0.0,
            "their_laser_t": min([f.laser_t for f in foes if f.laser_t is not None] or [None]) if not laser else 0.0,
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
        print(f"time to die (losses): median {statistics.median(r['survive_t'] for r in l_):.1f} s")
    for who, sk, hk in (("we", "shots", "hits"), ("they", "their_shots", "their_hits")):
        parts = []
        for wpn in ("gun", "laser", "lightning", "mortar"):
            sh = sum(r[sk].get(wpn, 0) for r in rs)
            ht = sum(r[hk].get(wpn, 0) for r in rs)
            if sh:
                parts.append(f"{wpn} {ht}/{sh} = {100 * ht / sh:.0f}%")
        print(f"hit rate ({who}): " + (", ".join(parts) or "no shots"))
    def by_range(sd, hd):
        out = []
        for lo, hi in ((0, 50), (50, 100), (100, 150), (150, 250)):
            a = sum(1 for x in sd if lo <= x < hi)
            b = sum(1 for x in hd if lo <= x < hi)
            if a:
                out.append(f"{lo}-{hi} m {100 * b / a:.0f}% ({a})")
        return ", ".join(out)
    print("their gun hit rate by range: " + by_range([d for r in rs for d in r["their_shot_d"]], [d for r in rs for d in r["their_hit_d"]]))
    print("our gun hit rate by range:   " + by_range([d for r in rs for d in r["our_shot_d"]], [d for r in rs for d in r["our_hit_d"]]))
    if any(r["our_laser_t"] for r in rs) or any(r["their_laser_t"] for r in rs):
        ol = [r["our_laser_t"] for r in rs if r["our_laser_t"]]
        tl = [r["their_laser_t"] for r in rs if r["their_laser_t"]]
        print(f"laser picked up: us in {100 * len(ol) / n:.0f}% (median {statistics.median(ol) if ol else 0:.0f} s), "
              f"them in {100 * len(tl) / n:.0f}% (median {statistics.median(tl) if tl else 0:.0f} s)")
    if any(r["kills"] for r in rs) and rs[0].get("kills") is not None:
        print(f"kills per duel {statistics.mean(r['kills'] for r in rs):.2f}; survival median "
              f"{statistics.median(r['survive_t'] for r in rs):.1f} s")
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
    ap.add_argument("--vs", type=int, default=1, help="number of expert house bots (1v1, 1v2, ...)")
    ap.add_argument("--loot", action="store_true", help="normal floor loot and crates on the map")
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
            jobs = [(s, nm, dict(loader.VERSIONS), a.laser, a.time, a.level, a.vs, a.loot)
                    for s in range(a.seed, a.seed + a.duels)]
            results[nm] = sorted(pool.imap_unordered(one, jobs), key=lambda r: r["seed"])
            report(nm, results[nm])
    if len(names) > 1:
        base = {r["seed"]: r["res"] for r in results[names[0]]}
        for nm in names[1:]:
            bk = {r["seed"]: r["kills"] for r in results[names[0]]}
            dk = [r["kills"] - bk[r["seed"]] for r in results[nm]]
            print(f"\n{nm} vs {names[0]}: kills per duel {statistics.mean(dk):+.3f}"
                  f" (se {statistics.stdev(dk) / math.sqrt(len(dk)) if len(dk) > 1 else 0:.3f})")
            better = sum(1 for r in results[nm] if r["res"] == "win" and base[r["seed"]] != "win")
            worse = sum(1 for r in results[nm] if r["res"] != "win" and base[r["seed"]] == "win")
            print(f"\n{nm} vs {names[0]} (same seeds): wins gained {better}, wins lost {worse}"
                  f" -> net {better - worse:+d} of {len(results[nm])} (sign test: clear if |net| > 2*sqrt(gained+lost)"
                  f" = {2 * math.sqrt(max(better + worse, 1)):.1f})")
    print(f"\n({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
