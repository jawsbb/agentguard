# Known Issues

This is an early **alpha** (`0.1.0`). The three blocking bugs found during the
initial audit are already fixed in the first commit (store ordering, the
`protect(strategy=...)` README example, and the `redis://` failure mode).

The items below are known limitations that are **not yet addressed**. They are
tracked here so the README does not oversell capabilities that aren't wired up
yet. Contributions welcome.

## Features advertised but not fully wired

- **Cost tracking is inert.** `AgentGuard.get_stats()["total_cost"]` is always
  `$0.0000`. In the main `protect`/`action` path, `detector.end_action()` is
  called without a `cost` argument, so the cost-spike anomaly never fires and
  `stats.total_cost` is never incremented. Needs a way to feed per-action token
  cost into the guard.
- **Anomaly-driven recovery is not connected.** `RecoveryConfig.strategy_map`
  and `RecoveryEngine.get_strategy_for_anomaly()` exist but are never consulted
  by the guard, which uses a single fixed strategy per call. The `SIMPLIFY`,
  `DIFFERENT_MODEL`, and `ROLLBACK` strategies currently only sleep — there is
  no prompt simplification or model switching behind them yet (the README's
  "model switching" claim is aspirational).
- **`checkpoint.guard()` restore semantics.** On exception it restores the
  checkpoint it created *on entry* (the about-to-run state), not the prior safe
  state. Worth revisiting whether this is the intended rollback behavior.

## Dead / unused code

- `GuardConfig` (in `core/guard.py`) is defined but never instantiated;
  `AgentGuard.__init__` takes individual keyword args instead.
- `protect(timeout=...)` is accepted but not applied to execution.

## Quality / hygiene

- **Pydantic v2 deprecation.** `CheckpointData` uses the v1-style
  `class Config`, which emits a `DeprecationWarning`. Switch to
  `model_config = ConfigDict(arbitrary_types_allowed=True)`.
- **Test coverage gaps.** Only `checkpoint` (and `SQLiteStore`) are tested.
  `detector`, `recovery`, `guard`, and `cli` have no tests yet.
- **`_safe_serialize` pickle path.** It can emit pickled-hex blobs that are
  never decoded back on restore; loading arbitrary pickles is also a security
  consideration.
- **Metadata inconsistencies.** `CONTRIBUTING.md` is referenced from the README
  but does not exist; the `docs/` directory is empty; the PyPI badge /
  `pip install agentguard` imply a published package that isn't on PyPI yet.

## Operational notes

- `SQLiteStore` opens a new connection per operation with no WAL mode or
  cross-thread coordination — fine for a single local agent, not for concurrent
  multi-process access.
