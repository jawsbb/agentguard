"""Recovery with model switching.

Demonstrates how AgentGuard's recovery strategies do real work: register a
callback for DIFFERENT_MODEL and AgentGuard will run it before the retry, so the
next attempt uses a different model.
"""

from agentguard import AgentGuard, RecoveryStrategy

ag = AgentGuard(store="memory", max_retries=3, set_as_default=False)
ag.recovery.config.base_delay = 0.0  # no backoff delay for the demo

# Shared state the callback mutates between attempts.
client = {"model": "expensive-primary"}

FALLBACKS = ["cheaper-fallback", "tiny-last-resort"]


def switch_model(attempt: int, error: Exception) -> None:
    """Pick the next fallback model after a failure."""
    idx = min(attempt - 1, len(FALLBACKS) - 1)
    client["model"] = FALLBACKS[idx]
    print(f"  ! attempt {attempt} failed ({error}); switching to {client['model']}")


ag.on_recover(RecoveryStrategy.DIFFERENT_MODEL, switch_model)


@ag.protect(strategies=[RecoveryStrategy.DIFFERENT_MODEL])
def generate(prompt: str) -> str:
    model = client["model"]
    # Pretend the primary model is overloaded but fallbacks work.
    if model == "expensive-primary":
        raise ConnectionError("primary overloaded")
    return f"[{model}] -> response to {prompt!r}"


if __name__ == "__main__":
    print("Calling generate() with automatic model switching:\n")
    result = generate("summarize the audit")
    print("\nResult:", result)
    print("\nStats:")
    for k, v in ag.get_stats().items():
        print(f"  {k}: {v}")
