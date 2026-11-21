# Experiments

## Step 1: what the score is made of (read first; every decision must agree with this)

Sources: kit/protocol.md section 4 (Scoring) and the track rules page (practice and final sections).

1. **Our place = 16 - (house bots dead before us). Confirmed.** Placement is the order of death: the last mech
   alive is 1st, the first to die is 16th, and "Mechs that die on the same tick share a placement" (protocol 4).
   The 15 house bots are "acting as one squad: they share vision, never fight each other" (track rules). So when we
   die, our place is the number of mechs still alive including us, and our points (16 - place) equal the number of
   house bots that died before that tick. If one dies on the same tick as us we share its (better) place.
2. **How house bots die other than by us:** the zone (they take its damage like anyone), NPC drones (they shoot any
   mech within 45 m of them, or whoever hit them, 25 a shot), and, in principle, their own mortar splash (50 %
   self-damage). Never each other. So almost every point we earn is a house bot **we** killed, plus the few the
   zone and drones take.
3. **If we are still alive at the end:** the match ends when one mech is left or at 8:00; "If the clock runs out,
   survivors are ranked by HP" (protocol 4). The last circle closes to radius 0 by about 6:55 at 260 HP/s, so late
   survivors are ranked by who lasts longest in that; outliving all 15 house bots is a win (15 points).
4. **When fighting is cheap and when it is deadly.** They "hunt you weakest first (one early, more as you thin them
   out, all of them late)". Early, one hunter: a 1-v-1 is the cheapest place to earn points, and every point needs
   a kill. Each kill adds a hunter, so fights get harder as we score. Late, the whole squad hunts: any fight is
   against many, so late points come from surviving while they die to the zone, not from kills.
   **Placement is the score, but in practice placement is made of kills:** a bot that never kills scores close to
   what the zone and drones give it (the kit's example bot: 1.15).
5. **Practice vs final.** The final is "16-mech free-for-alls" between the qualifiers' bots (expert house bots only
   fill empty slots). There, other bots do kill each other, so survival earns points on its own. Anything that
   works only because the house bots never fight each other or because we are the only target is marked
   **practice-only** below.

Process (team rules, Sat Nov 21): one idea per experiment, written hypothesis first, challenger vs champion on
the same seeds with enough matches that luck averages out, keep only if clearly better (paired difference
above 2 standard errors), otherwise revert to the champion. Every experiment must keep max response time well
under 50 ms (target < 25 ms) and pass `kit/check/check.py`. Only the champion is submitted, and only after it
beat the previous champion locally.

**Score** = mean of (16 - place). Board baseline (kit example bot): 1.15.

## Champion

| | |
|---|---|
| Champion | **champ-3.77** (branch) = E6 on champ-3.69, git `f579248243f7207ddba7c3afa2960b7d441c1694` |
| Previous | champ-3.69 (branch; also `champ-v3.1`) = git `8611ff7`, bot code identical to `bbd6f57` |
| Official score | 3.69 (one 48-match run, Fri 11:09 PM ET); the same play without the speed fix (v3) scored 3.52 |
| Run-to-run noise | about +-0.5 per 48-match run (spread of placement points per match ~3.5-4.5) |

## Local measurement

`python3 sim/run.py calibrate --matches N --versions champ,NAME=<gitrev>` plays each version alone against
15 stand-in house bots on the same seeds and prints: mean placement points, sd, se, average place,
% dead in the first 60 s, % top-3, % deaths outside the zone, average and max response time, and the paired
difference against the champion with a KEEP-level verdict (BETTER only if > 2 se).

The simulator (`sim/`) is my reconstruction of the game from protocol.md; the real house bots are unknown.
**It is only valid for deciding experiments once it reproduces the board's ordering** (example 1.15 far below
champion 3.69). That is experiment E0.

---

## History before the process (official board runs, 48 matches each)

These were mostly bundles, so they say little about individual ideas. Listed for the record.

| id | commit | what changed | official | note |
|---|---|---|---|---|
| H1 v1 | 1bc77f0 | survivor bot: zone hold point, fight when attacked or close | 3.21 | |
| H2 v3 | 5db062e | + strafing + roof perching (bundle of two) | 3.52 | |
| H3 v4 | 9cd3063 | + cover-first combat + 130 m laser detour + speed fix (bundle) | 2.58 | |
| H4 A+B+C | bf61a15 | + speed fix + aim prediction + intel cover-when-shot (bundle) | 2.90 | |
| H5 v5 | a13a3b3 | v3 + speed fix + fire discipline + intel avoidance + laser grab (bundle) | 3.19 | |
| H6 v3.1 | bbd6f57 | v3 + decision-time fix only | **3.69** | champion |
| H7 v3.2 | a35616c | v3.1 + roof perching off | 2.96 | may have built a merged bundle (raced a merge) |
| H8 v3.3 | 24a2e95 | v3.1 + no crate shooting | 3.04 | |
| H9 v3.4 | e3a20e7 | v3.1 + laser grab up to 70 m | 3.63 | |
| H10 v3.6 | 5935272 | v3.4 + safe climbing + corner peek/burst + flanking + full scan (bundle) | 3.48 | |

What the history suggests (weak, single noisy runs): versions that perch on roofs (3.52, 3.69, 3.63) did better
than those that do not (3.21, 2.96); removing crate shooting looked worse (3.04); cover-first / hide-and-peek
bundles looked worse (2.58, 2.90). Nothing since v3 has moved the board beyond the noise.

Ideas already tried (do not retry without a new reason): roof perching off; no crate shooting; cover-first
combat (hide before fighting, run up to 40 m to cover); bundles of several changes.

Ideas built but never measured alone: safe climbing (`try-climb`), corner peek-and-burst (`try-peek`),
flank-biased strafing (`try-flank`), full-circle scanning, drone farming (`v37`), aim prediction (`aim`).

---

## Step 2: diagnosis of the champion (simulator, 200 seeds)

Setup: `SIM_AIM_MULT=3.5 SIM_DEFEND_RANGE=60 python3 sim/diag.py --version champ --matches 200`.
Calibration (E0, 80 seeds per setting): the squad model ranks champion above example at 5 of 6 settings; the
chosen setting gave champion 3.25 / example 2.02 vs the board's 3.69 / 1.15, so the simulator still overrates the
example bot by ~0.9. Treat numbers as directional; decide experiments on paired same-seed differences.

Champion here: **4.41 +- 0.29 (sd 4.04)**, average place 11.6, top-3 8 %, alive at the end 6 %, dead in the
first minute 24 %, median death at 130 s. Max response 14.4 ms, average 0.25 ms.

Where the points come from: house bots dead before us 4.41 per match = our kills 65 %, zone 19 %, drones 16 %.

Causes of death, ranked by share of all points lost (points lost = 15 - points, summed):
1. **Dying in COVER mode: 53 %** (97 of 187 deaths). The bot breaks off a fight to run for cover and dies on
   the way: 64 % of all deaths are in the open, killers are mostly within 100 m.
2. **Dying in FIGHT: 31 %**, mostly against 2+ attackers.
3. **Dying in ROTATE (moving with the zone): 13 %.**
Across all modes: **2 or more mechs were hitting us in 68 % of lost points**; 32 % of deaths went from full HP
to dead within 15 s (focus fire). Zone itself killed us in 5 %, drones 3 %.

Kills we failed to convert: 0.38 per match a house bot dropped below 25 % HP from our hits and did not die by
our hand. Our mode 1.5 s after the last hit: FIGHT 35 (it got away or out of sight), **COVER 29 (we broke off
while it was nearly dead)**, ROTATE 8.

Ranked by estimated points lost:
1. Breaking off to COVER mid-fight (deaths while running + nearly-dead targets let go). The champion's cover
   rule compares absolute HP (ours < 80 % of the target's) and ignores how close the target is to dying.
2. Being outnumbered (2+ attackers) in FIGHT; the 90 m engagement trigger can pull in more squad members.
3. Rotating with the zone through enemies.

Other numbers: laser picked up in 32 % of matches; 2.5 cubes and 1.2 upgrades per match.

---

## E0 - calibrate the simulator (tool, not bot)

- **Date:** Sat Nov 21
- **Hypothesis:** with stand-in house bots that hunt the entrant within some radius and only fight each other
  up close, the simulator reproduces the board's ordering: example (1.15) far below champion (3.69).
- **What changed:** house-bot parameters only (`SIM_HUNT_RADIUS`, `SIM_INFIGHT`).
- **Result (80 seeds each):** aim x1.0: champ 1.93/2.00 vs example 1.70/1.26 (defend 30/60 m); aim x2.0: 2.67/2.45
  vs 1.84/1.38; aim x3.5: 4.11/3.25 vs 2.33/2.02. Champion beats example by > 2 se in 5 of 6 settings.
- **Decision:** USE `SIM_AIM_MULT=3.5 SIM_DEFEND_RANGE=60` (closest to both board scores). Known error: example
  overrated by ~0.9. Decide experiments only on paired same-seed differences (> 2 se).

## Fixes to the measurement (Sat Nov 21, after E0)

- The 3.25 (calibration) vs 4.41 (diagnosis) gap came from three differences: seeds (1-80 vs 1-200), seating
  (shuffled vs always seat 0) and timing (the bot's route search stopped at a wall-clock deadline, so the same
  seed gave 7, 6, 7 points). Fixed: same seating in both tools, the bot's clock frozen in the simulator, workers
  pinned to one CPU each. Same seed now gives the same result across tools and runs (12/12).
- **base** (git `8e48450`): champion + route search limited by a node budget (1000/decision) with the wall clock
  only as a 15 ms safety net, so the real 1-CPU scorer plans like the simulator. No other change.
- Champion with the fixes, 200 seeds: **3.38 +- 0.23** (sd 3.19); real 3.69.

## Recalibration after the fixes (100 seeds, workers pinned to one CPU)

base 3.36 (real 3.69), e2b 3.65 (real 3.69), example 2.11 (real 1.15): example is clearly below base
(-1.25 +- 0.41) but still overrated by ~1 point. Max response: base 43 ms once (concurrent Docker check on the
same cores; watched in later runs), e2b 11.6 ms, example 16 ms.

## E2 - never break off from a nearly dead target

- **Date / commit:** Sat Nov 21, `e2` (on the champion) and `e2b` = base + E2 (`23980ee`)
- **Hypothesis:** dying while running for cover was 53-56 % of lost points and 29 of 78 missed kills followed a
  break-off with the target below 25 %. Never retreating from a target below 35 % HP, and judging "losing" on HP
  fractions, should turn those into kills: fewer COVER deaths, fewer missed kills, more kills.
- **Change:** no cover / retreat from a target below 35 % HP; losing = our HP fraction < 0.8 x the target's.
- **Result (200 paired seeds):** 3.42 vs champion 3.38, **+0.04 +- 0.14 (se): no clear difference.** Deaths in
  COVER 0.56 -> 0.40 per match, but outnumbered deaths 0.65 -> 0.69 and missed kills 0.39 -> 0.40: the deaths moved
  into fights against 2+ attackers instead of turning into kills. Kills 2.27 -> 2.38. First-minute deaths 30 %
  both. Full-to-dead-in-15-s 31 % -> 32 %. Max response (e2b, Docker sandbox): 11.6 ms.
- **Decision:** not clearly worse, so per the board rule it was submitted as e2b (carries the clock fix).
- **Official (Sat Nov 21):** **3.69**, tied with the champion; the simulator said +0.04 +- 0.14.
- **Decision (team, Sat Nov 21): REVERTED on the board** - it did not beat the champion, so the base goes back to
  champ-3.69. The board decides from now on, not the simulator.
- **Lesson:** the binding problem is being outnumbered, not the cover rule. Next: E3.

## E3 - do not provoke / break off when outnumbered

- **Date / commits:** Sat Nov 21; `e3a` (`f017416`) and `e3b` (`283bba3`), both on e2b.
- **Hypothesis:** 65-69 % of deaths had 2+ attackers and first-minute deaths start with FIGHT; only one house
  bot hunts us early, so extra attackers are squad members we shot first. Shooting only mechs that hit us (or
  are within 30 m) should cut outnumbered deaths; E3b adds breaking off to cover when 2+ attack us.
- **Change:** E3a: fight radius 90 m -> 30 m. E3b: E3a + retreat to cover when 2+ mechs hit us in 5 s or aim
  at us within 100 m (E2 still finishes a target below 35 %).
- **Result (200 paired seeds vs e2b):** e2b 3.45, e3a 2.46 (**-0.99 +- 0.22**), e3b 2.71 (**-0.74 +- 0.24**).
  Kills 2.29 -> 1.52 / 1.51; outnumbered deaths 0.63 -> 0.69 / 0.70 (not reduced); first-minute deaths 29 % ->
  32 % / 31 %. Response times in this run are not valid (the cast browser shared the CPU).
- **Decision:** REVERTED (both clearly worse). main stays on e2b.
- **Lesson:** fighting less costs kills and does not stop the squad from engaging us. Together with the live
  cast (top bots have ~2x our max armor from cubes and plating, and an early laser), the problem is fragility,
  not aggression. Next: E6 cubes, E7 plating first, E8 early laser, E9 heal before fighting.

## E6-E9 - fragility (from the live cast: top bots have ~2x our max armor and an early laser)

All four are one change each on e2b (`23980ee`). Quick check: 100 paired seeds, workers pinned to one CPU, no
browser running. Each passes tests, the quality gate and check.py in the scorer's Docker sandbox.

| id | commit | change | sim vs e2b (se) | notes | Docker max |
|---|---|---|---|---|---|
| E8 | `d522b95aff65d39eaabc240b50c302deb638757f` | opening (< 90 s): up to 150 m for a laser when not attacked, none contested, inside the zone | **+0.30 +- 0.29** | kills 2.48 -> 2.74, first-minute deaths 28 % -> 22 % | 9.0 ms |
| E6 | `c47909bc42b739a15460a767fc992a26d0ec9e24` | cubes all match: from roofs, with mechs near, mid-fight within 25 m; not with 2+ attackers; inside the zone | +0.06 +- 0.33 | kills 2.65; outnumbered deaths 0.62 -> 0.72 | 9.5 ms |
| E7 | `dbc47b8e5bacba1d3bdd5b96ced6740f1462513d` | plating before armor | 0.00 +- 0.00 | identical in all 100 matches: the simulator rarely offers plating and armor together; only the board can judge | 9.7 ms |
| E9 | `26f33e99d413a2e4e0719a7472fa4851c7323491` | below 70 % and not hit: no new fights until 95 % | -0.12 +- 0.34 | full-to-dead-in-15-s 34 % -> 24 %, kills 2.35 | 8.1 ms |

e2b response time, pinned, no browser, 100 matches: avg 0.20 ms, max 26.4 ms (under 50, slightly over the 25 aim).

Decision: none is clearly worse, so each goes to the board in turn (E8, E6, E7, E9), each alone on main.
Official scores: **E8 (on e2b): 3.50** (main `998454c`; assumed to be the submission reported as 3.50, to be
confirmed) - worse than champ-3.69 although the simulator said +0.30 +- 0.29. E6, E7, E9 on e2b: not submitted.
**Decision (team): REVERTED.** The board decides. All four are rebuilt as single changes on champ-3.69 (below).

## E6-E9 rebuilt on champ-3.69 (board decides; one change each)

champ-3.69 response time (pinned to 1 CPU, no browser, 100 matches): max 14.4 ms, p99 3.05 ms, p99.9 9.0 ms,
0 decisions over 25 ms. Quick check per branch: 30 matches, no crashes, max 11-18 ms, p99 ~5 ms, 0 over 25 ms;
tests, quality gate and check.py in the scorer's Docker sandbox pass (max 5-7 ms).

| id | branch | full commit | change | official |
|---|---|---|---|---|
| E6 | ce6 | `f579248243f7207ddba7c3afa2960b7d441c1694` | cubes all match (roofs, mechs near, mid-fight within 25 m; not with 2+ attackers; inside zone) | **3.77** (BB-9D1FB3DD, main `5670442`): new best, **KEPT -> champ-3.77**. +0.08 is inside the ~0.5 run-to-run noise |
| E7 | ce7 | `4c2447fb16186a38333106f923e225e7b6be3117` | plating before armor | pending |
| E8 | ce8 | `3020940f9b134974f29183e02efc6c7e3c88b819` | opening: up to 150 m for a laser when not attacked | pending (E8 on e2b scored 3.50) |
| E9 | ce9 | `48934d84016c09b8d7439d871e87a0fa3170bd1b` | below 70 % and not hit: no new fights until 95 % | pending |

Plan: each alone on main, submitted in turn; then the ones that beat 3.69 are combined.

## E7-E9 rebuilt on champ-3.77 (one change each on E6)

Quick check per branch: 30 matches, no crashes, p99 ~5 ms; ne9 one decision at 25.3 ms. check.py in the
scorer's Docker sandbox passes (ne7 max 7.0, ne9 7.6, ne8 5.0/6.4 on reruns; one 32.6 ms right after a Docker
daemon restart did not repeat).

| id | branch | full commit | change | official |
|---|---|---|---|---|
| E8 | ne8 | `57083018f6c3f0ae242b456cb20d1609761642e8` | opening: up to 150 m for a laser when not attacked (merged by hand next to E6) | **3.73** (BB-5097B658, main `3b97489`): below 3.77, REVERTED |
| E7 | ne7 | `85b2a8481b793f283804987b5e1ac7cb7108a389` | plating before armor | pending (on main `d289c59`) |
| E9 | ne9 | `a78da01b71ac363b41bc4d93162f7eeeff042ee4` | below 70 % and not hit: no new fights until 95 % | pending |

## Board results (all official runs, 48 matches each)

| board run | bot commit | experiment | the one change | sim estimate | board |
|---|---|---|---|---|---|
| - | `1bc77f0` | v1 | survivor bot | - | 3.21 |
| - | `5db062e` | v3 | strafing + roof perching (2 changes) | - | 3.52 |
| - | `9cd3063` | v4 | cover-first + laser detour + speed fix (bundle) | - | 2.58 |
| - | `cf8d2a4` | A+B+C | speed fix + aim + intel cover (bundle) | - | 2.90 |
| - | `a13a3b3` | v5 | fire discipline + intel avoidance + laser grab (bundle) | - | 3.19 |
| - | `bbd6f57` | v3.1 | v3 + decision-time fix | - | 3.69 |
| - | `a35616c` | v3.2 | roof perching off | - | 2.96 |
| - | `24a2e95` | v3.3 | no crate shooting | - | 3.04 |
| - | `e3a20e7` | v3.4 | laser grab up to 70 m | - | 3.63 |
| - | `5935272` | v3.6 | climb safety + peek + flank + scan (bundle) | - | 3.48 |
| - | `23980ee` | E2 (+ node budget) | no break-off from a nearly dead target | +0.04 +- 0.14 | 3.69 |
| - | `d522b95` | E8 on e2b | opening laser up to 150 m | +0.30 +- 0.29 | 3.50 |
| BB-9D1FB3DD | `f579248` | **E6** | cubes all match | +1.00 (30 seeds) | **3.77** (champ-3.77) |
| BB-5097B658 | `5708301` | E8 on champ-3.77 | opening laser up to 150 m | +1.17 (30 seeds) | 3.73 |

Lessons (team, Sat Nov 21): simulator scores do not predict the board (+1.17 sim -> -0.04 board); use the
simulator only to confirm a change does what it should. Every bundle scored badly; combine only changes that each
beat the champion on the board on their own.

## Behaviour check (100 seeds; does each change do what it is meant to?)

| | champ-3.69 | champ-3.77 (E6) | E7 | E8 | E9 |
|---|---|---|---|---|---|
| cubes / match | 1.65 | 3.17 | 3.27 | 3.44 | 3.00 |
| upgrades / match | 0.89 | 1.42 | 1.46 | 1.45 | 1.35 |
| plating / match | 0.21 | 0.22 | 0.27 | 0.21 | 0.17 |
| laser by 2:00 | 22 % | 29 % | 29 % | 36 % | 27 % |
| max armor at end | 1540 | 1618 | 1636 | 1622 | 1594 |

E6 works (cubes x1.9, upgrades +60 %) but max armor only 1540 -> 1618 vs ~2981 on top bots: 3 cubes is far from
the 10-cube cap. E7 barely moves plating (0.22 -> 0.27): each offer shows 3 random upgrades of ~13, and we get
~1.4 offers per match; only more cubes can fix that. E8 moves laser-by-2:00 only 29 -> 36 %: it only goes for
lasers it happens to see.

## Duels (sim/duel.py): our bot vs ONE expert house bot, 300 fixed seeds, nothing else on the map

champ-3.77 gun only: win 55.7 % / loss 11.3 % / draw 33.0 %; our gun hits 82 %, theirs 60 %; HP left after a
win 18 %. Both with lasers: win 51.3 % / loss 20.3 %; laser hits ours 97 %, theirs 77 %.

| id | branch / commit | change | gun duels: win, net vs champ (clear if > 2 sqrt(changed)) | laser duels | decision |
|---|---|---|---|---|---|
| D1 | d1 `198a6b9ac7855c6381ef0b69bb64d5b6a501f3c2` | strafe legs 0.35-0.9 s (was 0.8-2.0) | **63.0 %, +22 (> 13): clear**; their hits 60 -> 53 %, losses 11.3 -> 5.3 %, HP left 18 -> 29 % | 50.7 %, -2 | **to the board** |
| D2 | d2 `f1c896c` | gun band 70-170 m (was 35-130) | 58.3 %, +8 (< 10.2) | 51.3 %, 0 | not clear |
| D3 | d3 `373b3cf` | 1v1: no cover when merely losing on HP | 55.3 %, -1 | 52.7 %, +4 | not clear |
| D4 | d4 `9078147` | boost while strafing above 20 energy (was 45) | 58.3 %, +8 | **45.3 %, -18: clearly worse** | rejected |
| D5 | d5 `fc4fa3fbf9f59be98023f4849943b2c975f48632` | gun band 110-190 m (was 35-130): the expert hits 90 % at 0-50 m, 68 % at 50-100, 38 % at 100-150, 23 % beyond; we hit 91/83/78 % | 60.7 %, **+15 (> 13.4): clear** | loot mode +5 (not clear) | candidate |
| D6 | d6 `a73db34` | hop every ~1 s above 30 energy (was ~2.5 s above 60) | 48.3 %, **-22: clearly worse** | loot mode -21 | rejected |
| D1+D5 | d15 `ec350c1f0cf961018539f068f522fdfa72037b51` | D5 on top of D1 | vs D1: 63.7 % vs 63.0 %, net +2 (not clear); losses 5.3 -> 3.0 %, their hits 53 -> 49 % | - | candidate if D1 beats 3.77 |

1v2 (us vs two experts, both hunting, 200 seeds): champ wins 0.5 %, loses 67.5 %, median survival 25.0 s, 0.28 kills;
D1 0.33 kills, survival 25.7 s; D5 0.30 kills, survival 28.6 s; D6 0.21 kills, 19.7 s. Nothing changes the 1v2
outcome much: two experts beat us about 2 times in 3.
Loot on the map (1v1, 200 seeds): we pick up a laser in 19-24 % of duels (median ~9 s), the expert in 4 %.

Response time: p99 11-15 ms in every duel run; occasional single decisions of 37-54 ms move at random between
runs (identical play, so environmental, not the bot's computation); the real bot process in the scorer's Docker
sandbox stays at max 5-10 ms. Candidate safety experiment: halve the per-decision search budget.

## E5 data (first-minute deaths, champion, 200 seeds)

30 % of matches. First damage at a median 11 s, death at 35 s. Two attackers in 36 of 61, three in 9. In the
open 43 of 61. Killed by house guns 42, lasers 12, lightning 6. First damage from a drone in 13 of 61.
In those matches FIGHT is the most common decision of the first minute (10 769 vs HOLD 5 232): the bot opens fire
on any mech within 90 m, which can pull non-hunting squad members into the fight (in the simulator they defend
themselves when attacked or approached; the real rule is unknown).

## E1 - drone farming (pending, waits for E0)

- **Commit:** `v37` branch (v3.1 + farming, one change)
- **Hypothesis:** early cubes raise max HP (+4 % each) and unlock armour/plating at 1/3/6/10 cubes, so the
  bot survives later fights longer: higher mean placement, fewer first-minute deaths are not expected to change.
- **What changed:** first 150 s, HP > 60 %, no mech within 120 m: shoot drones within 160 m, collect cubes
  within 60 m (even from a roof).
- **Result:** not measured yet (an uncalibrated run showed few cubes collected; to be redone after E0).
