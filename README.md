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
first. So the bot plays for position: it picks the safest strong spot in each ring, prefers height, fights only when
something is close enough to be a real threat, and never gets caught by the zone.

### Position (`position.py`)

At `hello` the map yields a catalogue of **perches**: building roofs at least 6 m high with room to strafe at least
one cell (3 m) from every edge, and the free ground cells beside each building to jet up from. Roofs higher than a
full tank can climb (80 % of `max_energy x max_rise_speed / jet_drain` plus the jump, about 56 m) are skipped; that
excludes the 70 m towers, as the protocol says. Each time the next circle is announced (and every 8 s after,
with hysteresis) every perch and a lattice of ground spots inside the next circle (with a 12 m margin) is scored:

| Term | Weight | Why |
|---|---|---|
| height of the roof (capped at 30 m) | +1.2 | see over buildings, shoot down, out of drone reach |
| room on the roof | +0.3 | strafe without falling off |
| walls around a ground spot | +0.5 | a wall at our back blocks shots and sight |
| distance from the circle's centre / radius | -0.7 | later circles fall inside this one |
| travel time / time left before the shrink ends | -1.0 | spots we cannot reach in time are dropped |
| visible mechs within 80 m, drones within 55 m | -0.8 each, -0.6 each | do not walk into a fight |
| it is the spot we already hold | +0.25 | do not flip-flop |

To get up, the bot walks to the building's foot, waits until its energy covers the climb plus 15, then jumps and
jets into the wall until its feet clear the edge (protocol section 7: a taller ledge is a wall until your feet are
above it) and steps onto the roof. If it is not up within 7 s that roof is avoided for 60 s and another spot is chosen.
On a roof every move, strafe and cover search is checked against the roof's own cells, so it holds the height.

### Rules, first match wins (`plan.py`)

| Mode | When | What it does |
|---|---|---|
| `ROTATE` | outside the current (interpolated) circle, or the shrink would catch us with < 8 s slack | boost toward the spot, still shooting back |
| `FIGHT` | a mech hit us in the last 4 s, a mech is within 90 m (135 m with 3 or fewer mechs left), or a drone is within its 45 m aggro range or hit us | face it, shoot, strafe (see Evasion); on a roof it fights from the roof |
| `COVER` | in a FIGHT where the enemy has a laser and we don't (beyond 60 m), or we are losing on HP | nearest point within 36 m the attacker cannot see; on a roof, a point back from the edge |
| `ALERT` | hit by something we cannot see | turn to the damage bearing, keep moving |
| `LOOT` | on the ground travelling, before 260 s, no enemy within 120 m, not pulling us away from the spot | better weapon (laser > lightning > mortar), cube, uncontested close supply drop, crate (HP >= 70 %) |
| `HOLD` / `CLIMB` / `PERCH` | otherwise | walk to the spot / climb onto it / stand on it silently, sweeping the 120 degree view cone and facing any visible mech without shooting it |

## Evasion (`_evade`)

Whenever the bot shoots at a mech or drone, or a mech hit it in the last 4 s or is aiming at it, it never stands still:
strafe legs across the line of fire with random length (0.8-2.0 s) so the enemy cannot time its lead, boost while
energy is above 45, a hop every ~2.5 s while energy is above 60, a push to keep the best weapon's range band
(gun 35-130 m, laser 60-200 m, lightning 12-38 m), and an immediate reversal when a wall is within 6 m on the
strafe side. The one exception is real cover: at the COVER spot with no line of sight from the attacker it stays put
to regenerate; if the attacker can still see it there, it strafes and searches for new cover.

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
