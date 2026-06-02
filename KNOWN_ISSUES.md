# Known Issues

This is an early **alpha** (`0.1.0`). The three blocking bugs found during the
initial audit are already fixed in the first commit (store ordering, the
`protect(strategy=...)` README example, and the `redis://` failure mode).

The items below are known limitations that are **not yet addressed**. They are
tracked here so the README does not oversell capabilities that aren't wired up
yet. Contributions welcome.

## Recently fixed

- **Cost tracking now works.** Use `guard.record_cost(usd)` (when the cost is
  known after the call) or `guard.action(name, cost=usd)`. Both update
  `stats.total_cost` and feed the cost-spike detector. ✅
- **Pydantic v2 deprecation removed** — `CheckpointData` now uses
  `model_config = ConfigDict(...)`. ✅
- **Test coverage added** for the detector, recovery engine, guard
  orchestrator, and the CLI (62 tests). ✅
- **Recovery strategies now do real work.** Register a transform with
  `guard.on_recover(strategy, callback)` and pass an escalation plan via
  `@guard.protect(strategies=[...])`. The callback runs before the next attempt
  (e.g. switch model / simplify prompt). `RecoveryEngine.execute_for_anomaly()`
  drives recovery from `strategy_map`. See `examples/model_switching.py`. ✅
- **`protect(timeout=...)` is now applied** — a slower-than-`timeout` call is
  flagged as a TIMEOUT anomaly (post-hoc; the call is not killed). ✅
- **CLI `list` no longer shadows the builtin.** It was named `list`, which made
  `status`/`rollback --dry-run` crash on their `list(...)` calls. Fixed. ✅
- **Removed the unsafe pickle path** in `_safe_serialize` (pickled blobs were
  never decoded and unpickling untrusted data is a risk) — non-JSON values now
  serialize to a safe `repr` marker. ✅
- **Removed dead `GuardConfig`** dataclass. ✅

## Features advertised but not fully wired

- **Anomaly type does not auto-select the strategy in the guard path.** The
  building blocks exist (`strategy_map`, `execute_for_anomaly`,
  `get_strategy_for_anomaly`), but `guard.protect`/`action` still need the
  caller to pass `strategies=`. Auto-selecting the plan from a live anomaly
  would require detecting the anomaly *during* execution rather than at
  `end_action` (post-hoc). Callbacks are also required for SIMPLIFY/
  DIFFERENT_MODEL to have an effect — without one they degrade to a plain retry.
- **`checkpoint.guard()` restore semantics.** On exception it restores the
  checkpoint it created *on entry* (the about-to-run state), not the prior safe
  state. Worth revisiting whether this is the intended rollback behavior.

## Quality / hygiene

- **Metadata inconsistencies.** The `docs/` directory is empty; the PyPI badge /
  `pip install agentguard` imply a published package that isn't on PyPI yet.

## Operational notes

- `SQLiteStore` opens a new connection per operation with no WAL mode or
  cross-thread coordination — fine for a single local agent, not for concurrent
  multi-process access.
