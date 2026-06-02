# Contributing to AgentGuard

Thanks for your interest in improving AgentGuard! This is an early-stage
project, so contributions of all sizes are welcome — bug reports, docs,
tests, and features.

## Development setup

```bash
git clone https://github.com/jawsbb/agentguard
cd agentguard
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before you open a PR

Run the same checks CI runs:

```bash
ruff check src/ tests/ examples/   # lint
pytest -q                          # tests
```

Both must pass. CI runs them on Python 3.10, 3.11, and 3.12.

## Guidelines

- **Keep it honest.** Don't document a capability that isn't wired up. If a
  feature is partial, note it in [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).
- **Add tests** for new behavior — the suite covers the checkpoint, detector,
  recovery, and guard modules; please keep that coverage up.
- **Match the existing style.** `ruff` enforces formatting/import rules
  (line length 100, rules `E`, `F`, `I`, `N`, `W`, `UP`).
- **Small, focused commits** with a clear message are easier to review.

## Good first issues

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for a curated list of known gaps —
several (CLI tests, `GuardConfig` cleanup, `CONTRIBUTING` polish, the
`_safe_serialize` pickle round-trip) are approachable starting points.

## Reporting bugs

Open an issue with a minimal reproduction, the AgentGuard version
(`agentguard version`), and your Python version. A failing test is the most
useful bug report of all.
