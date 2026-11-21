# goonies: Mech Royale bot

Our entry for the Builders Buildathon **Mech Royale** track: the AI for one mech in a 16-mech battle royale on the
Ohio State campus, speaking the `mechfight/1` protocol (JSON lines on stdin/stdout, one decision every 0.1 s, 50 ms
budget each). Score = mean of `16 - place` over 48 practice matches against house bots. Baseline (kit example bot):
**1.15**.

The repository follows the layout of
[prebuilt-ai-technique-models](https://github.com/KennethLei1492/prebuilt-ai-technique-models):
the bot reasons first and then acts (`plan()` before `execute()`, with the plan auditable), every tunable sits in one
config whose defaults cite the rule they come from, tests run offline and give the same result every run, and one
quality gate must pass before each submission.

```
Dockerfile                    top level, as the track requires (copies bot/ and arena/)
bot/main.py                   entrypoint: mf.run(MechBot)
bot/mechfight.py              kit wrapper, unchanged (stdin/stdout loop, newest-obs rule, debug drawing)
bot/mechbot/
  config.py                   BotConfig: every tunable, each default justified by a protocol.md section
  plan.py                     Plan + HeuristicPlanner: ordered, explainable rules -> mode, goal, target, rationale
  model.py                    MechBot: Memory -> plan -> cover -> movement -> aim/fire -> upgrades/pickups
  worldmap.py                 map model from arena/v2: terrain, 3 m walkability grid, line of sight, resumable A*
  ballistics.py               lead for straight shots, mortar elevation, angle helpers
arena/v2/                     the static map (also mounted read-only at /arena in a match)
kit/                          protocol.md, schema, check/check.py + recorded match stream, example bot
tests/                        offline pytest suites (map, ballistics, planner rules, full replay)
tools/quality_gate.py         pytest + static checks + check.py (local and in the Docker match sandbox)
docs/ARCHITECTURE.md          the contract the code follows
docs/research/mech-royale.json  dossier: rules as verified from the kit, assumptions, leaderboard snapshot
```

## Architecture

```
obs ─▶ Memory.ingest (who hit us, from where, loud sounds)
     ─▶ HeuristicPlanner.plan ──▶ Plan(mode, goal, target, boost, retreat, face_bearing, take, rationale)
     ─▶ _maybe_cover            (a bad fight becomes COVER: nearest spot the attacker cannot see)
     ─▶ _move                   A* path to goal · strafe in fights · laser-dodge · drone avoidance · wall probe · unstick (jump+jet, detour)
     ─▶ _aim_fire               lead (gun) · direct + hold/release (laser) · cone check (lightning) · ballistic arc (mortar) · LOS gate
     ─▶ _offer / _take          upgrade by survival priority · take better weapons, swapping slot 1
     ─▶ action {tick, move, boost, jump, aim, fire, pick, take, drop, debug.label = rationale}
```

## How it reasons about an observation

Scoring rewards **surviving**, not kills (`16 - place`), and the house bots share vision and hunt the weakest entrant
first. The plan is therefore: keep HP high, stay out of fights we do not need, never get caught by the zone, and
win the fights we cannot avoid by facing the attacker (rear hits deal x1.5).

Rules, first match wins (`plan.py`):

| Mode | When | What it does |
|---|---|---|
| `ROTATE` | outside the current (interpolated) circle, or the shrink would catch us with < 8 s slack | boost to the hold point, still shooting back |
| `FIGHT` | a mech hit us in the last 4 s, or one is within 110 m, or one under 40 % HP within 180 m, or 3 or fewer mechs remain | face it, strafe, shoot; retreat below 35 % HP if it has more HP |
| `COVER` | in a FIGHT where the enemy has a laser and we don't (beyond 60 m), or we are losing on HP | run to the nearest walkable point within 36 m that the attacker's eye has no line of sight to |
| `ALERT` | hit by something we cannot see | turn to the damage bearing, keep moving |
| `LOOT` | before 260 s, no enemy within 120 m, not pulling us away from the zone | better weapon (laser > lightning > mortar), cube, uncontested close supply drop, crate (HP ≥ 70 %) |
| `HOLD` | otherwise | walk to the hold point (55 % of the next circle's radius on our side; 35 % when it is ≤ 70 m) and stand silently, sweeping the 120° view cone, facing any visible mech |

## Quick start

```bash
python3 tools/quality_gate.py            # tests + static checks + conformance check
python3 tools/quality_gate.py --docker   # also builds the image and checks it in the match sandbox
```

## Configuration (`BotConfig`)

Game numbers (speeds, ranges, damage, zone phases) are read live from `hello.config`, as protocol.md section 6
requires. `BotConfig` only holds our strategy choices; every field has its justification in a comment in
`bot/mechbot/config.py`.

## Evaluation

There is no local simulator: `check.py` replays a recorded match that does not react to our actions. What we can
measure locally (the gate does all of it):

- protocol conformance and latency, locally and inside the exact match sandbox (p99 about 12 ms against the 50 ms budget);
- the map model against reality: 468 of 469 recorded mech positions fall on walkable cells, terrain within 5 mm of recorded feet heights;
- ballistic solutions hit moving targets in closed form;
- each planner rule on hand-built observations, and the full decision loop over the recorded match (it takes cover against
  the laser mech that killed the recording bot).

Play quality is measured only by the practice board (48 matches per submission, 4 submissions an hour). Record every
submission's commit and score in `docs/research/mech-royale.json` under `submissions`.

## Limitations

- No local game: tuning needs board submissions. A simulator would be the biggest gain next.
- The grid treats roofs as walls; the bot never paths over buildings on purpose (unstick jets over low ones).
- Mortar aiming ignores walls along the arc; incoming mortar shells are not dodged.
- Sound is used only to turn toward nearby gunfire.

## How it was built

1. **Research.** Read the track page, protocol.md and the kit; checked every rule we rely on against `hello.config`
   in the kit's recorded match (`docs/research/mech-royale.json`).
2. **Critique.** Replayed the recorded match: the kit bot (13th place) lost about 950 HP to three 315-damage laser
   shots from 150 m that it answered with a gun. That made cover, not dodging, the response to lasers.
3. **Verify.** Map model, ballistics and planner rules are covered by tests; `tools/quality_gate.py` gates every
   submission.
