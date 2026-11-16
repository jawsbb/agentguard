# AgentGuard

**Checkpoint, detect, recover — make any AI agent production-ready.**

[![CI](https://github.com/jawsbb/agentguard/actions/workflows/ci.yml/badge.svg)](https://github.com/jawsbb/agentguard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## Why

Reliability, not capability, is what keeps agents out of production. The math is
unforgiving: a 10-step workflow where each step is **85%** reliable succeeds
end-to-end only **0.85¹⁰ ≈ 20%** of the time. One flaky tool call, one infinite
loop, one runaway cost spike — and the whole run is lost.

Most agent frameworks optimize for what an agent *can* do. AgentGuard adds the
missing reliability layer underneath:

- **Checkpoint** state before risky steps, and roll back on failure.
- **Detect** loops, timeouts, cost spikes, and error cascades as they happen.
- **Recover** automatically with retries, backoff, model switching, or escalation.

It's a small, dependency-light library you drop in with a decorator — no
infrastructure, no SaaS.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       Your Agent                        │
│           (LangChain, CrewAI, custom loops, ...)        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   AgentGuard Middleware                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Checkpoint  │  │   Detector   │  │   Recovery   │   │
│  │    Engine    │  │    Engine    │  │    Engine    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install agentguard
```

Or from source:

```bash
pip install git+https://github.com/jawsbb/agentguard
```

For local development:

```bash
git clone https://github.com/jawsbb/agentguard
cd agentguard
pip install -e ".[dev]"
```

## Quick Start

### Decorator (simplest)

```python
from agentguard import guard

@guard
def risky_operation(prompt):
    return agent.execute(prompt)

# Checkpoints before running, retries with backoff on failure
result = risky_operation("do the thing")
```

### Context manager

```python
from agentguard import AgentGuard

ag = AgentGuard(store="sqlite:///agent.db", max_retries=3)

with ag.action("code_execution", state={"files": files}):
    result = agent.run_code(code)
    # State is rolled back automatically if the block raises
```

### Manual checkpoint / rollback

```python
from agentguard import AgentGuard

ag = AgentGuard()

ag.save("before_deploy", state={"version": "1.0", "config": config})
try:
    deploy()
except DeploymentError:
    state = ag.rollback()
    print(f"Rolled back to version {state['version']}")
```

## Features

### Anomaly detection

| Anomaly | Description | Default threshold |
|---------|-------------|-------------------|
| **Loop** | Same action repeated N times | 5 repetitions |
| **Timeout** | Action exceeds time limit | 30 seconds |
| **Cost spike** | Per-action cost anomaly | $0.10 / action |
| **Error cascade** | Consecutive failures | 3 errors |
| **Drift** | Output diverges from an expected pattern | configurable |
| **Hallucination** | Low model confidence | confidence < 0.3 |

Detection is currently *post-hoc*: an anomaly is flagged after the action
completes (it is recorded and counted, the call is not killed mid-flight).

### Recovery strategies

```python
from agentguard import RecoveryStrategy

@ag.protect(strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF)
def api_call():
    ...

# Strategies:
#   RETRY · EXPONENTIAL_BACKOFF · ROLLBACK · SIMPLIFY
#   DIFFERENT_MODEL · HUMAN_ESCALATE · SKIP · ABORT
```

`SIMPLIFY` and `DIFFERENT_MODEL` only do real work when you register a callback
that transforms the next attempt. Register one with `guard.on_recover(...)` and
supply an escalation plan via `strategies=[...]`:

```python
# Switch to a fallback model after a failure, then retry
guard.on_recover(
    RecoveryStrategy.DIFFERENT_MODEL,
    lambda attempt, error: client.use_fallback_model(),
)

@guard.protect(strategies=[RecoveryStrategy.RETRY, RecoveryStrategy.DIFFERENT_MODEL])
def generate(prompt):
    return client.complete(prompt)
```

The plan lists recovery actions *between* attempts (`plan[0]` runs after the
first failure). See [`examples/model_switching.py`](examples/model_switching.py)
for a runnable end-to-end example.

### Cost tracking

Report the cost of an action so AgentGuard can total it and flag spikes:

```python
@guard.protect
def call_llm(prompt: str) -> str:
    resp = llm.complete(prompt)
    guard.record_cost(resp.usage.cost_usd)  # learned after the call
    return resp.text

# or attach a known cost to a block
with guard.action("batch_job", cost=0.25):
    run_batch()

print(guard.get_stats()["total_cost"])  # "$0.2500"
```

### CLI

```bash
agentguard status              # recent checkpoints
agentguard list                # list checkpoints
agentguard show <id>           # checkpoint details (id or prefix)
agentguard rollback <id>       # restore a checkpoint (--dry-run to preview)
agentguard stats               # database statistics
agentguard clear --force       # wipe all checkpoints
```

## Configuration

```python
from agentguard import AgentGuard

ag = AgentGuard(
    store="sqlite:///agent.db",  # or "memory" (redis:// coming soon)
    cost_limit=1.0,              # USD per run
    timeout=30.0,                # seconds per action
    max_loops=5,                 # repeated-action threshold
    max_retries=3,
    auto_recover=True,
    verbose=True,
)
```

## Observability

```python
stats = ag.get_stats()
# {
#   "total_actions": 42,
#   "successful_actions": 40,
#   "failed_actions": 2,
#   "recovered_actions": 3,
#   "success_rate": "95.2%",
#   "anomalies_detected": 3,
#   "checkpoints_created": 42,
#   "rollbacks_performed": 2,
#   "total_cost": "$0.1234",
#   "runtime": "12.3s",
# }
```

## Integrations

AgentGuard wraps any Python callable, so it works with any agent framework today
via the decorator or context manager:

- **Custom agent loops** — `@guard.protect` / `with guard.action(...)`
- **LangChain · CrewAI · LlamaIndex** — wrap your tool or step functions

First-class adapters and a Claude Code MCP server are planned — see the roadmap.

## Why AgentGuard?

| | Temporal | LangSmith | AgentGuard |
|---|---|---|---|
| Focus | Generic workflows | LLM observability | Agent reliability |
| Setup | Infrastructure | SaaS | `pip install` |
| Recovery | Manual | None | Automatic |
| Open source | Partial | No | 100% MIT |

## Roadmap

- [x] Core checkpoint / restore
- [x] Anomaly detection (loop, timeout, cost, error cascade, drift)
- [x] Recovery strategies with transform callbacks
- [x] Cost tracking
- [x] SQLite + in-memory storage
- [x] CLI
- [ ] Redis storage
- [ ] In-flight anomaly detection (kill/recover mid-action)
- [ ] Claude Code MCP server
- [ ] Web dashboard & webhook alerts
- [ ] Multi-agent coordination

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Known gaps and
good first issues are tracked in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

```bash
pip install -e ".[dev]"
ruff check src/ tests/ examples/    # lint
pytest -q                           # 62 tests
```

## License

MIT — see [LICENSE](LICENSE).

---

Built by [@jawsbb](https://github.com/jawsbb) · [Level Up](https://levelup.run) & [Fabrik](https://fabrik.ai)
