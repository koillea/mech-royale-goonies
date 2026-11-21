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
| Champion | **champ-3.69** (branch; also `champ-v3.1`) = git `8611ff7`, bot code identical to `bbd6f57` |
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

## E0 - calibrate the simulator (tool, not bot)

- **Date:** Sat Nov 21
- **Hypothesis:** with stand-in house bots that hunt the entrant within some radius and only fight each other
  up close, the simulator reproduces the board's ordering: example (1.15) far below champion (3.69).
- **What changed:** house-bot parameters only (`SIM_HUNT_RADIUS`, `SIM_INFIGHT`).
- **Result:** pending.
- **Decision:** the simulator may decide experiments only if, at the chosen setting, champion beats example by
  more than 2 se over 100+ seeds.

## E1 - drone farming (pending, waits for E0)

- **Commit:** `v37` branch (v3.1 + farming, one change)
- **Hypothesis:** early cubes raise max HP (+4 % each) and unlock armour/plating at 1/3/6/10 cubes, so the
  bot survives later fights longer: higher mean placement, fewer first-minute deaths are not expected to change.
- **What changed:** first 150 s, HP > 60 %, no mech within 120 m: shoot drones within 160 m, collect cubes
  within 60 m (even from a roof).
- **Result:** not measured yet (an uncalibrated run showed few cubes collected; to be redone after E0).
