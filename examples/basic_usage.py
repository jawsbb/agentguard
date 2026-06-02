"""Basic AgentGuard usage example."""

from agentguard import AgentGuard, RecoveryStrategy, guard, recover

# Initialize AgentGuard
ag = AgentGuard(
    store="sqlite:///example.db",
    cost_limit=0.50,  # USD
    max_retries=3,
    timeout=30.0,  # seconds
    verbose=True,
)


# Example 1: Using the @guard decorator
@guard
def risky_api_call(prompt: str) -> str:
    """Simulated API call that might fail."""
    import random

    if random.random() < 0.3:  # 30% chance of failure
        raise ConnectionError("API temporarily unavailable")
    return f"Response to: {prompt}"


# Example 2: Using the @protect decorator with options
@ag.protect(name="code_execution", timeout=60)
def execute_code(code: str) -> dict:
    """Execute code with protection."""
    # Simulated code execution
    result = eval(code)  # Don't do this in real code!
    return {"result": result, "code": code}


# Example 3: Using context manager
def process_files(files: list[str]) -> list[str]:
    """Process files with checkpoint protection."""
    results = []

    for file in files:
        with ag.action(f"process_{file}", state={"file": file, "results_so_far": results}):
            # Simulated file processing
            results.append(f"Processed: {file}")

    return results


# Example 4: Manual checkpoint and rollback
def deploy_with_rollback():
    """Deploy with manual checkpoint control."""
    # Save state before deployment
    ag.save("pre_deploy", state={
        "version": "1.0.0",
        "config": {"debug": False},
        "services": ["api", "web", "worker"],
    })

    try:
        # Simulated deployment
        print("Deploying...")
        # deploy_to_production()

        # If something goes wrong
        # raise RuntimeError("Deployment failed!")

        print("Deployment successful!")

    except Exception as e:
        print(f"Deployment failed: {e}")
        # Rollback to pre-deployment state
        state = ag.rollback()
        print(f"Rolled back to version: {state['version']}")


# Example 5: Using recover() for simple retry
def fetch_data_with_retry():
    """Fetch data with automatic retry."""
    import random

    def unstable_fetch():
        if random.random() < 0.5:
            raise TimeoutError("Request timed out")
        return {"data": [1, 2, 3]}

    # Will retry up to 3 times with exponential backoff
    result = recover(
        unstable_fetch,
        max_retries=3,
        strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
    )
    return result


if __name__ == "__main__":
    print("=== AgentGuard Examples ===\n")

    # Run examples
    print("1. Risky API call with auto-retry:")
    try:
        result = risky_api_call("Hello, world!")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Failed: {e}")

    print("\n2. Code execution with protection:")
    try:
        result = execute_code("2 + 2")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Failed: {e}")

    print("\n3. File processing with checkpoints:")
    results = process_files(["file1.txt", "file2.txt", "file3.txt"])
    print(f"   Results: {results}")

    print("\n4. Deployment with rollback:")
    deploy_with_rollback()

    print("\n5. Fetch with retry:")
    try:
        data = fetch_data_with_retry()
        print(f"   Data: {data}")
    except Exception as e:
        print(f"   Failed after retries: {e}")

    # Show final stats
    print("\n=== Statistics ===")
    for key, value in ag.get_stats().items():
        print(f"   {key}: {value}")
