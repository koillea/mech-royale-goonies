# Architecture and implementation contract

The rules every change to the bot follows (adapted from prebuilt-ai-technique-models `docs/ARCHITECTURE.md`).

## Life cycle
1. `MechBot.act(obs)` always runs `Memory.ingest -> HeuristicPlanner.plan -> execute`. No decision is taken outside a `Plan`.
2. `plan()` reads the observation and returns a `Plan` with a human-readable `rationale`; the rationale is sent as
   `debug.label` so every decision can be audited in our debug recordings.
3. `execute` (the `_move`, `_aim_fire`, `_offer`, `_take` phases) carries out the plan and never raises: the wrapper
   would re-send the last move, but a crash in a phase must not cost a decision.

## Rules
- **Read the rules from `hello.config`**, never hard-code game numbers (balance changes between matches). Defaults in
  code are fallbacks only.
- **Budget:** each decision stays well inside 50 ms on one CPU. Anything long (A*) is resumable and spread across
  decisions with a per-call node budget. The hello work (map build) stays under 2 s of the 20 s budget.
- **stdout is the protocol.** Logs go to stderr only (`model.log`). The gate fails on any bare `print()` in `bot/`.
- **Standard library only.** The container has no network; nothing is installed.
- **Sandbox:** write only to `/tmp`, run as uid 65534, read the map from `hello.map.dir` (falls back to the bundled copy).
- **Strategy tunables live in `BotConfig`** with a comment naming the rule or evidence behind each default.

## Testing
- Tests are offline and give the same result every run: the kit's recorded match plus hand-built observations.
- Cover: map model against recorded positions, ballistics in closed form, each planner rule, the full replay
  (valid actions, latency, expected modes).
- `python3 tools/quality_gate.py --docker` must pass before every submission.

## Iteration loop (the board is the only real evaluator)
1. One change per submission. 2. Gate passes. 3. Push, submit, record commit + score in the dossier.
4. Keep the best-scoring commit tagged (`git tag best-<score>`); fall back to it if a change scores worse.
