# AgentGuard

**Checkpoint, detect, recover — make any AI agent production-ready.**

[![PyPI version](https://badge.fury.io/py/agentguard.svg)](https://badge.fury.io/py/agentguard)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## The Problem

**88% of AI agents never reach production.** Not because of bad models, but because of reliability failures.

Even at 85% reliability per step, a 10-step workflow succeeds only **20% of the time**. Most agent frameworks focus on capabilities, not reliability.

AgentGuard fixes this.

## What It Does

```
┌─────────────────────────────────────────────────────────┐
│                      Your Agent                         │
│            (Claude Code, Hermes, OpenClaw...)           │
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

- **Checkpoint**: Save state before risky operations, rollback on failure
- **Detect**: Catch loops, timeouts, cost spikes, and error cascades in real-time
- **Recover**: Intelligent retry with exponential backoff, model switching, or escalation

## Installation

```bash
pip install agentguard
```

## Quick Start

### Decorator (simplest)

```python
from agentguard import guard

@guard
def risky_operation():
    return agent.execute(prompt)

# Automatically checkpoints, retries on failure, rolls back if needed
result = risky_operation()
```

### Context Manager

```python
from agentguard import AgentGuard

ag = AgentGuard(
    store="sqlite:///agent.db",
    cost_limit=0.50,
    max_retries=3,
)

with ag.action("code_execution", state={"files": files}):
    result = agent.run_code(code)
    # Auto-rollback on exception
```

### Manual Control

```python
from agentguard import AgentGuard

ag = AgentGuard()

# Checkpoint before dangerous action
ag.save("before_deploy", state={"version": "1.0", "config": config})

try:
    deploy()
except DeploymentError:
    # Restore previous state
    state = ag.rollback()
    print(f"Rolled back to version {state['version']}")
```

## Features

### Anomaly Detection

AgentGuard automatically detects:

| Anomaly | Description | Default Threshold |
|---------|-------------|-------------------|
| **Loop** | Same action repeated N times | 5 repetitions |
| **Timeout** | Action exceeds time limit | 30 seconds |
| **Cost Spike** | Token usage anomaly | $0.10/action |
| **Error Cascade** | Consecutive failures | 3 errors |
| **Drift** | Output diverges from pattern | Configurable |

### Recovery Strategies

```python
from agentguard import RecoveryStrategy

@ag.protect(strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF)
def api_call():
    ...

# Available strategies:
# - RETRY: Simple retry
# - EXPONENTIAL_BACKOFF: Increasing delays
# - ROLLBACK: Restore checkpoint
# - SIMPLIFY: Retry with simpler prompt
# - DIFFERENT_MODEL: Try alternative model
# - HUMAN_ESCALATE: Pause for human input
# - SKIP: Continue without this step
```

Strategies like `SIMPLIFY` and `DIFFERENT_MODEL` only do real work when you
register a callback that transforms the next attempt. Register one with
`guard.on_recover(...)` and supply an escalation plan via `strategies=[...]`:

```python
# Swap to a fallback model after a failure, then retry
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

### Cost Tracking

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
# View status
agentguard status

# List checkpoints
agentguard list

# Show checkpoint details
agentguard show <checkpoint-id>

# Rollback
agentguard rollback <checkpoint-id>

# Statistics
agentguard stats
```

## Configuration

```python
from agentguard import AgentGuard

ag = AgentGuard(
    # Storage
    store="sqlite:///agent.db",  # or "memory" (redis:// coming soon)

    # Limits
    cost_limit=1.0,              # USD per run
    timeout=30.0,                # seconds per action
    max_loops=5,                 # repeated action threshold

    # Recovery
    max_retries=3,
    auto_recover=True,

    # Debug
    verbose=True,
)
```

## Integrations

AgentGuard works with any Python-based agent:

- **Claude Code** — via MCP server (coming soon)
- **Hermes Agent** — direct integration
- **LangChain** — as a callback handler
- **CrewAI** — as middleware
- **Custom agents** — decorator or context manager

## Why AgentGuard?

| Feature | Temporal | LangSmith | AgentGuard |
|---------|----------|-----------|------------|
| Focus | Generic workflows | LLM observability | Agent reliability |
| Setup | Infrastructure required | SaaS | `pip install` |
| Recovery | Manual | None | Automatic |
| Open Source | Partial | No | 100% MIT |
| Agent-aware | No | Yes | Yes + recovery |

## Stats & Observability

```python
# Get runtime statistics
stats = ag.get_stats()
print(stats)
# {
#     "total_actions": 42,
#     "successful_actions": 40,
#     "success_rate": "95.2%",
#     "anomalies_detected": 3,
#     "rollbacks_performed": 2,
#     "total_cost": "$0.1234",
# }
```

## Roadmap

- [x] Core checkpoint/restore
- [x] Anomaly detection (loops, timeouts, cost)
- [x] Recovery strategies
- [x] SQLite storage
- [x] CLI
- [ ] Redis storage
- [ ] Web dashboard
- [ ] MCP server integration
- [ ] Webhook alerts
- [ ] Multi-agent coordination

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Setup dev environment
git clone https://github.com/jawsbb/agentguard
cd agentguard
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

## License

MIT License — see [LICENSE](LICENSE) for details.

---

Built by [@jawsbb](https://github.com/jawsbb) | [Level Up](https://levelup.run) & [Fabrik](https://fabrik.ai)
