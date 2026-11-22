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
| Champion | **champ-3.81** (branch) = E7 on champ-3.77 (plating first), git `85b2a8481b793f283804987b5e1ac7cb7108a389` |
| Before | champ-3.77 = E6 (cubes all match), git `f579248243f7207ddba7c3afa2960b7d441c1694` |
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
| E7 | ne7 | `85b2a8481b793f283804987b5e1ac7cb7108a389` | plating before armor | **3.81** (BB-91CB1D0E): new best, **KEPT -> champ-3.81** (+0.04, inside the noise) |
| E9 | ne9 | `a78da01b71ac363b41bc4d93162f7eeeff042ee4` | below 70 % and not hit: no new fights until 95 % | **3.79** (BB-859410C2): below 3.81, REVERTED |

## B1-B3 - bold single changes on champ-3.81 (board decides)

Each is ONE behaviour change on champ-3.81 (`85b2a8481b793f283804987b5e1ac7cb7108a389`). Sim runs (30 seeds,
`SIM_AIM_MULT=3.5 SIM_DEFEND_RANGE=60`) only check that the change does what it says and stays fast; they do not decide.

| id | branch / commit | change | sim behaviour check | Docker check.py max | board |
|---|---|---|---|---|---|
| B1 | b1 `7bef6b1fd32e422250c3cc09d5d6f5f63347116c` | roof sniper: perch only on roofs >= 12 m, height weighted x3, engage out to 230 m (gun) / 280 m (laser) from the roof, no cube runs while perched | checked by tests/test_b1.py (roof-height choice, wider target radius when perched); no sim metrics logged | 8.3 ms | **3.88**: new best (+0.07, inside the ~0.5 noise), **KEPT -> champ-3.88** |
| B2 | b2 `98ba5b53d95f80042b6263cb74e39ebc54388a10` | drone kiting: when a hunter chases and shoots us (> 30 m), run on a route that passes 48-65 m from a known drone so the hunter's line cuts within 40 m of it (inside its 45 m aggro); boost if energy > 30 | 3.63 -> 3.77 (+0.13, se 0.56, noise); full-to-dead in 15 s 38 -> 30 %, median death 110 -> 143 s | 7.1 ms | **3.73**: below 3.81, REVERTED |
| B3 | b3 `e304ae68b3e52ec801ee67a07314f28b01ae1edf` | chokepoint defence: no roof perches; hold precomputed high-cover cells (>= 10 cover, hold 12 m) and keep the spot while fighting | outnumbered deaths 0.70 -> 0.57, missed kills 0.40 -> 0.27 | 6.5 ms | **3.79**: below 3.81, REVERTED |

Only B1 beat the champion, so nothing to combine. Next bold step goes on champ-3.88 (branch `champ-3.88` = B1).

| id | branch / commit | change | sim behaviour check | Docker check.py max | board |
|---|---|---|---|---|---|
| B4 | b4 `a84f4d82f8ad92fdd8c7531b0ccd5b71bb6dffe2` | roof first: while walking to a roof's wall or climbing it, start no fight with a mech that has not hit us unless it is within 30 m (was 90 m) | 3.63 -> 3.17 (-0.47, se 0.43, noise); kills 2.53 -> 2.27, COVER deaths 0.43 -> 0.63 | 10.4 ms | pending |

Rule: anything below the champion on the board is reverted; only changes that each beat 3.81 alone get combined.

## Full-offense plan (O1-O3), cube plan (C1-C3) and the minimal bot (M1-M3) - Sun Nov 22

**Sim update (step 0).** protocol.md says nothing about what the house bots know of our position; the user saw on
the real board that they always know it, so `sim/house.py` now makes them omniscient (default; `SIM_OMNISCIENT=0`
restores the old shared-vision model). Cube facts from protocol.md section 10: a killed mech drops all its cubes
plus 2 (a drone 2, a crate 1); the protocol gives no lifetime for cubes (weapons explicitly never despawn) and no
scatter radius (the sim puts them within 3 m). Max armour 2,981 seen on top bots = 1,400 x 1.4 (10 cubes, the
stat cap) x 1.15^3 (plating, max 3 stacks): the maximum possible.
New sim telemetry: hit rate by range and by target motion, time-to-kill (our first hit -> its death), cubes at
20 s / 60 s, rear hits taken, time in each mode, crashes; `SIM_CFG_<name>` overrides a version's BotConfig.

**Time-to-kill is fire-rate bound, not aim bound (sim).** The gun sustains 12 x 45 / (12 x 0.24 + 2.4) = 102
damage/s, so 1,400 HP takes >= 13.7 s at 100 % hits; at our 80 % it is 17 s, the measured median. Laser adds
~131/s (hitscan), lightning ~240/s inside 45 m; both slots fire together.

Duels (300 seeds, omniscient expert hunters):

| | 1v1 win | gun hit rate | median TTK | 1v2 kills | 1v3 kills | dmg taken per kill (1v2) |
|---|---|---|---|---|---|---|
| champ-3.81 | 64.7 % | 80 % | 16.9 s | 0.29 | - | 4,804 |
| O1 aim | 62.3 % (net -7, noise) | 81 % | 16.5 s | 0.34 | 0.18 | 4,228 |
| O2 offense (on O1) | 66.0 % (net +11 vs O1, noise) | 89 % | 13.2 s | 0.30 | 0.19 | 4,571 |

O1 ablation: the 0.05 s decision-delay term over-led (net -27 wins), so it was removed; acceleration + strafe
rhythm alone are level with the champion. O1 hit rate by target motion: still 88 %, strafing 84 %, jumping 76 %.

Full matches (sim, same seeds, omniscient house bots):

| id | commit | change | score | kills | cubes 20 s / 60 s / end | max armour | rear hits | max ms | board |
|---|---|---|---|---|---|---|---|---|---|
| champ-3.81 | `85b2a8481b793f283804987b5e1ac7cb7108a389` | - | 3.25 (40 seeds) | 2.02 | 0.88 / 1.62 / 2.27 | 1,552 | 4.2 | 18.6 | 3.81 |
| O1 | `9a6da6b9b4cf2a1e110c98f47fa6e94894d9bf66` | lead with acceleration, gravity, strafe rhythm | 3.42 (+0.17, se 0.54) | 2.40 | 0.88 / 1.48 / 2.88 | 1,599 | 4.9 | 13.0 | 3.54: below, REVERTED |
| O2 | `f37a2749c1a27d44791fac223c7bac01b8f614c7` | on O1: no cover/retreat, lock-on, engage all in range, close to 30-70 m, D1 legs | **1.88 (-1.38, se 0.46: WORSE)**; 65 % dead in the first minute | 1.40 | 0.45 / 1.15 / 1.20 | 1,490 | 5.6 | 14.7 | pending |
| C1 | `251394ff0b44a2b206082df31060e382b2590a39` | first 60 s: drones from 50-110 m, crates, cubes <= 120 m, laser; plating/armour then gun upgrades | **4.60 (+1.35, se 0.76)** | 3.12 | 1.10 / 3.35 / 5.80 | 1,785 | 5.6 | 19.8 | **4.19: NEW CHAMPION -> champ-4.19** (+0.38) |
| M1 | `305638e77d9aa6b3788a713801324a990a9be1ef` | separate ~300-line cube-first bot, no map (30 seeds) | 2.73 (-0.37 vs 3.10, se 0.75) | 1.87 | 0.57 / 2.33 / 3.87 | 1,692 | 7.2 | 0.6 | 3.69: below, not adopted |
| M2 | `4aa32ed6fdd64b61c976bcbeb451ea98913a17b5` | M1 + fight range 120 m | 2.80 (-0.30, se 0.77) | 1.87 | 0.37 / 1.77 / 3.03 | 1,659 | 4.7 | 0.5 | pending |
| M3 | `802d0b980514bc284c2ed3c5f887a721b8b0df37` | M1 + no farming after 90 s | 2.67 (-0.43, se 0.71) | 2.03 | 0.57 / 2.33 / 3.13 | 1,647 | 5.6 | 1.3 | pending |

M1 time in each mode (sim): FIGHT 33 %, CUBE 21 %, ROAM 10 %, DRONE 9 %, ZONE 8 %, CRATE 7 %, PICKUP 7 %, HEAL 5 %.
All pass kit check.py in Docker (max 5.6-7.0 ms for O/C, 1.1-2.8 ms for M). C2 and C3 are not built yet.

## C2-C6 - single changes on champ-4.19 (= C1, `251394ff0b44a2b206082df31060e382b2590a39`)

Rule from Sun Nov 22: the sim has mispredicted the board almost every time, so sim scores no longer decide
anything. The sim only confirms that a change does what it says; the board decides. Sim: 40 seeds,
omniscient house bots, same seeds as champ-4.19.

| id | branch / commit | change | behaviour check (champ-4.19 -> change) | cubes 20 s / 60 s / end | kills | rear hits | Docker max | board |
|---|---|---|---|---|---|---|---|---|
| champ-4.19 | `251394ff0b44a2b206082df31060e382b2590a39` | C1 cube opener | target switches 5.0/match | 1.10 / 3.35 / 5.80 | 3.12 | 5.6 | 5.9 ms | 4.19 |
| C2 | c2 `2cce593f3a689a91c605102a88f6c0c8b0d468ec` | focus fire: keep the lock until dead or out of sight 2 s, switch only to < 40 % HP | **switches 5.0 -> 1.2** | 1.10 / 3.38 / 5.33 | 2.48 | 7.2 | 6.4 ms | **3.69: REVERTED.** The sim flagged it (kills 3.12 -> 2.48, rear hits 5.6 -> 7.2): turning to face a new attacker matters more than finishing the current target |
| C3 | c3 `bb92088d664c01df6ed74a86c3590e2d275d7c81` | heal break: 2+ attackers in 3 s and HP < 50 %: cover facing them, hold fire, until 5 s without damage | **1.5 heal breaks/match**; COVER time 8 -> 12 %; dead in first 60 s 30 -> 20 % | 1.10 / 3.35 / 6.05 | 3.05 | 5.5 | 6.2 ms | **3.71**: below, dropped (pulls away from fights) |
| C4 | c4 `a660c5d51611449cabb847396140e0ec09a97300` | cube opener 120 s (was 60) | **cubes at end 5.8 -> 6.3**, LOOT time 26 -> 34 %, laser by 2:00 35 -> 47 % | 1.10 / 3.35 / 6.28 | 2.95 | 6.6 | 7.6 ms | 4.04: below, dropped |
| C5 | c5 `930e6f7354190dd3853ec5493e65f7d1afe85ef3` | opener goes up to 150 m for a laser (was 120) | **no change in any of 40 sim matches** (a laser seen at 120-150 m never came up); unit test confirms the rule | 1.10 / 3.35 / 5.80 | 3.12 | 5.6 | 6.8 ms | pending |
| C6 | c6 `f0773fde4f042ab0930a1cc7324dec49053ac071` | after every kill, go collect its cubes (still fighting) | **cubes within 20 s of a kill 2.95 -> 3.83**, cubes at 60 s 3.35 -> 3.75 | 1.10 / 3.75 / 6.20 | 2.85 | 5.1 | 5.4 ms | **4.42: NEW BEST -> champ-4.42** |

| C7 | c7 `5b2cd4477f4902f6a43fbf95dbd573ca947b598c` | faster opener: torso sweep (0.4 rad/decision) while nothing is targeted, 15 s memory of items seen, boost to items > 25 m, crates shot from <= 45 m, laser up to 130 m, opener moves before the roof climb | **cubes at 20 s 1.10 -> 1.48, at 60 s 3.35 -> 4.20**; laser by 2:00 35 -> 62 %; drones in view per decision 0.56 -> 1.01 | 1.48 / 4.20 / 5.75 | 3.40 | 5.9 | 6.4 ms | 4.04: below 4.19, dropped |

C7 note: the sim cannot reach the real game's 6 cubes by 18 s. Its map has ~60 cube sources (12 drones, 36
crates) over ~1 km2, about 3 sources (~4 cubes) within 120 m of a spawn, so ~2 by 20 s is near its ceiling.

Sim max decision time: 12-17 ms for all; one C6 run showed 30 ms with 6 versions in parallel, 16.9 ms when rerun
alone on the same seeds (machine load, not the bot). All pass kit check.py in Docker.

## C8, C9 and combinations - on champ-4.42 (= C6, `f0773fde4f042ab0930a1cc7324dec49053ac071`)

Sim: 40 seeds, behaviour check only (the board decides).

| id | branch / commit | change | behaviour check (champ-4.42 -> change) | kills | rear hits | Docker max | board |
|---|---|---|---|---|---|---|---|
| champ-4.42 | `f0773fde4f042ab0930a1cc7324dec49053ac071` | C6 kill cubes | cubes 6.20/match, 3.83 within 20 s of a kill | 2.85 | 5.1 | 5.4 ms | 4.42, 4.33 (two runs, avg ~4.38) |
| C8 | c8 `b915983b04cf35c01c366e65527e3cb5aec46597` | after the kill's cubes, collect other visible cubes within 60 m unless hit in the last 1.5 s | **cubes 6.20 -> 6.72, within 20 s of a kill 3.83 -> 4.22** | 3.05 | 5.5 | 7.3 ms | 4.23: below champ-4.42, DROPPED |
| C9 | c9 `316efa639796afad398fd2c89ed6750925140cb7` | target score + 40 per cube the target carries (attackers still +1000) | **no change in any of 40 matches**: sim house bots carry ~0.1 cubes (they do not farm); unit test confirms the rule | 2.85 | 5.1 | 6.5 ms | 4.23: below, dropped |
| C6+C3 | c6c3 `599e4094ae64b262eb795b4d12d30c6726c0fe7d` | combination (for if C3 beats 4.19) | heal breaks 1.7/match | **2.45** | **6.2** | 8.3 ms | pending |
| C6+C3+C4 | c6c3c4 `a03bf47a840dc366df57fc66d01efdc7a11ad61e` | combination (for if C3 and C4 beat 4.19) | heal breaks 1.8/match, cubes 6.50 | **2.20** | **7.4** | 5.5 ms | pending |

Pattern (Sun Nov 22, board): changes that pull the bot away from fights to collect or look around score worse
(C7 sweep/boost opener 4.04, C8 after-kill sweep 4.23); picking up the cubes right at the kill spot helps
(C6 4.42 / 4.33). C2 (3.69) showed that facing a new attacker matters more than finishing the current target.

Warning: both combinations show the pattern that preceded C2's drop (kills down, rear hits up). C3 turns away
from attackers to break line of sight.

## F1-F3 - "stay and fight", single changes on champ-4.42

Board lesson (Sun Nov 22): anything that pulls us away from fights hurts (C3 3.71, C4 4.04, C7 4.04, C8 4.23);
retreating lets the squad group up. Changes that fight better or take cubes where we already are help (C1, C6).
C9 (prefer cube carriers) 4.23.

| id | branch / commit | change | behaviour check (champ-4.42 -> change, 40 seeds) | cubes 20 s / 60 s / end | kills | rear hits | Docker max | board |
|---|---|---|---|---|---|---|---|---|
| F1 | f1 `2b8da9d75f8269e96f95ac13e1cd2d199df1ffc7` | no retreat: no low-HP back-off, no cover runs (range-band spacing kept) | **COVER time 8 % -> 0, FIGHT 33 -> 42 %**, kills 2.85 -> 3.30, cubes within 20 s of a kill 3.8 -> 5.4 | 1.10 / 3.92 / 7.72 | 3.30 | 5.9 | 5.8 ms | **4.48, 4.50 (avg ~4.49): CHAMPION -> champ-4.50** |
| F2 | f2 `f6771c7a2e9d789fc1f7283fa349cb84debadb3e` | a rear hit turns us to that attacker at once (unless our target < 25 % HP); unseen: turn to the bearing | **rear hits NOT down: 5.1 -> 5.5** (same ~12 % share of hits); missed kills 0.28 -> 0.15 | 1.02 / 3.73 / 6.65 | 2.88 | 5.5 | 7.4 ms | pending |
| F3 | f3 `9d2cfb9e425d332ca1cb72735c959e59e2c7628e` | after the first mech is seen, no farming except cubes within 15 m (C6 kill cubes kept) | **LOOT time 30 -> 12 %, cubes 6.2 -> 3.4**, cubes at 20 s 1.1 -> 0.6 | 0.60 / 1.90 / 3.42 | 2.48 | 4.7 | 7.3 ms | **3.38: DROPPED** (cutting farming costs ~1 point) |

Board summary so far: farm cubes early and at fights (+), never retreat (+), never wander far from fights for
items (-).

### Single changes on F1 = champ-4.50 (`2b8da9d75f8269e96f95ac13e1cd2d199df1ffc7`)

| id | branch / commit | change | behaviour check (F1 -> change, 40 seeds) | cubes 20 s / 60 s / end | kills | rear hits | Docker max | board |
|---|---|---|---|---|---|---|---|---|
| G1 | g1 `31d3c4bb2db834f3a2e571f4e9789afac434ea03` | opener: walking to a cube or laser, shoot a drone (50-110 m) or crate (<= 70 m) already in view, no detour | **cubes at 20 s 1.10 -> 1.38, at 60 s 3.92 -> 4.30** | 1.38 / 4.30 / 7.12 | 3.10 | 5.6 | 5.3 ms | 4.40: no gain over champ-4.50, DROPPED |
| G2 (= F4) | f4 `00308ff38d78fa163c4f79d6595ce607719b7dcd` | no spacing back-off: a mech inside the range band is held (strafe only), not backed off | unit test: F1 backs off west at -0.4, G2 holds; sim kills 3.30 -> 2.83 | 1.07 / 3.77 / 6.70 | 2.83 | 6.3 | 5.3 ms | pending |
| F1+F3 | f1f3 `eb20007417401798a4be41b65ad840d861e05213` | built before F3's board result; obsolete (F3 dropped) | - | 0.60 / 2.17 / 3.85 | 2.40 | 4.5 | 5.4 ms | not to submit |

Timing: sim max 17-25 ms for F1 and G1 alike on rerun (machine load: same seeds, same decisions as earlier 13-14 ms
runs); Docker check.py reruns 4.9-5.3 ms.

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
| BB-67C7DC0F | `198a6b9` | D1 on champ-3.77 | shorter strafe legs (0.35-0.9 s) | duels +22 net (clear) | 3.73 |
| BB-91CB1D0E | `85b2a84` | **E7** on champ-3.77 | plating before armor | not measurable in sim | **3.81** (champ-3.81) |
| BB-859410C2 | `a78da01` | E9 on champ-3.77 | heal before fighting | - | 3.79 |

Submissions are made by full commit hash from here on (main no longer needs to hold the submitted version).
All of E6-E9 and D1 landed within ~0.1 of 3.77: none really moved the score. D1's clear duel win did not
transfer. Next: bold single changes on champ-3.81 (roof sniper, zone/drone kiting, chokepoint defence).

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
