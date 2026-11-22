"""Per-match report from a real-game log (logs/real/<match>.jsonl written by the browser bridge).

    python3 sim/real_report.py logs/real/*.jsonl
"""
import collections, json, math, sys


def load(path):
    rows = []
    for line in open(path):
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def report(path):
    rows = load(path)
    obs = [r["m"] for r in rows if r["k"] == "obs"]
    if not obs:
        return None
    acts = [r for r in rows if r["k"] == "action"]
    sends = [r for r in rows if r["k"] == "send"]
    end = next((r["m"] for r in rows if r["k"] == "end"), {})
    res = next((r["m"] for r in rows if r["k"] == "results"), {})
    me_id = obs[0]["self"].get("id")
    cube_at = lambda T: max([o["self"]["cubes"] for o in obs if o["t"] <= T] or [0])
    laser_t = next((o["t"] for o in obs if any(w and w["kind"] == "laser" for w in o["self"]["weapons"])), None)
    dealt = taken = 0.0
    rear = hits_taken = 0
    dmg_log, my_shots = [], collections.Counter()
    hit_by_range = collections.defaultdict(lambda: [0, 0])
    for o in obs:
        for e in o.get("events", []):
            if e["type"] == "hit" and e.get("target", 0) < 100:
                dealt += e.get("amount", 0)
            if e["type"] == "damaged":
                taken += e.get("amount", 0)
                if e.get("by") is not None and e["by"] < 100:
                    hits_taken += 1
                    rear += 1 if e.get("rear") else 0
                dmg_log.append((o["t"], e.get("by"), e.get("weapon"), e.get("amount", 0), o["self"]["hp"]))
    labels = collections.Counter((r.get("label") or "?").split(" ")[0] for r in acts)
    slow = sum(1 for r in acts if (r.get("ms") or 0) > 50)
    fresh = sum(1 for r in sends if r.get("fresh"))
    last = obs[-1]
    died = end.get("place") is not None and last["self"]["hp"] <= 0 or (end and end.get("place", 1) > 1 and last["alive"] > 1)
    tdeath = last["t"]
    recent = [d for d in dmg_log if tdeath - d[0] <= 5]
    attackers = sorted({d[1] for d in recent if d[1] is not None and d[1] < 100})
    hp15 = [(round(o["t"], 1), round(o["self"]["hp"])) for o in obs if tdeath - o["t"] <= 15][::10]
    last_label = next((r.get("label") for r in reversed(acts) if r.get("label")), None)
    ms = sorted(r["ms"] for r in acts if r.get("ms") is not None)
    out = {
        "file": path.split("/")[-1], "place": end.get("place"), "kills": end.get("kills"), "duration": round(last["t"]),
        "dealt": round(dealt), "taken": round(taken), "cubes_20_60_end": (cube_at(20), cube_at(60), last["self"]["cubes"]),
        "laser_t": laser_t, "upgrades": last["self"].get("upgrades"), "rear_hits": rear, "mech_hits_taken": hits_taken,
        "decisions": len(acts), "over_50ms": slow, "ms_p50_p99_max": (ms[len(ms) // 2], ms[int(.99 * (len(ms) - 1))], ms[-1]) if ms else None,
        "sends_fresh": f"{fresh}/{len(sends)}", "modes": dict(labels.most_common(6)),
        "death_t": round(tdeath, 1), "attackers_last_5s": attackers, "last_plan": last_label,
        "damage_last_5s_by_weapon": dict(collections.Counter(d[2] for d in recent)),
        "hp_last_15s": hp15, "results": res.get("mechs", [])[:16] if isinstance(res.get("mechs"), list) else None,
    }
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        r = report(p)
        if r:
            res = r.pop("results")
            print(json.dumps(r, indent=1, default=str))
            if res:
                print("results:", json.dumps(res)[:1500])
