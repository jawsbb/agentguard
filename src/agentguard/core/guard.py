"""Main AgentGuard class that orchestrates checkpoint, detection, and recovery."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agentguard.core.checkpoint import Checkpoint
from agentguard.core.detector import Anomaly, AnomalyDetector
from agentguard.core.recovery import (
    RecoveryConfig,
    RecoveryEngine,
    RecoveryStrategy,
)
from agentguard.stores.sqlite import SQLiteStore

T = TypeVar("T")

# Global default guard instance
_default_guard: AgentGuard | None = None


def _get_default_guard() -> AgentGuard | None:
    """Get the default AgentGuard instance."""
    return _default_guard


def _set_default_guard(guard: AgentGuard) -> None:
    """Set the default AgentGuard instance."""
    global _default_guard
    _default_guard = guard


@dataclass
class GuardStats:
    """Runtime statistics."""

    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    recovered_actions: int = 0
    anomalies_detected: int = 0
    checkpoints_created: int = 0
    rollbacks_performed: int = 0
    total_cost: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        if self.total_actions == 0:
            return 0.0
        return self.successful_actions / self.total_actions

    @property
    def runtime_seconds(self) -> float:
        return time.time() - self.start_time


class AgentGuard:
    """
    Main orchestrator for agent reliability.

    Combines checkpointing, anomaly detection, and recovery into
    a unified interface for making AI agents production-ready.

    Usage:
        from agentguard import AgentGuard

        # Initialize
        guard = AgentGuard(
            store="sqlite:///agent.db",
            cost_limit=0.50,
            max_retries=3,
        )

        # Use as decorator
        @guard.protect
        def risky_operation():
            return agent.execute(...)

        # Use as context manager
        with guard.action("code_execution"):
            result = agent.run_code(code)

        # Manual control
        guard.checkpoint("before_deploy", state={...})
        try:
            deploy()
        except:
            guard.rollback()
    """

    def __init__(
        self,
        store: str = "sqlite:///agentguard.db",
        cost_limit: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
        max_loops: int = 5,
        auto_recover: bool = True,
        verbose: bool = False,
        set_as_default: bool = True,
    ) -> None:
        """
        Initialize AgentGuard.

        Args:
            store: Storage backend URI (sqlite:///path.db or redis://host:port)
            cost_limit: Maximum cost per action in USD
            max_retries: Maximum retry attempts
            timeout: Action timeout in seconds
            max_loops: Maximum repeated actions before anomaly
            auto_recover: Automatically attempt recovery on failure
            verbose: Enable verbose logging
            set_as_default: Set this as the default guard instance
        """
        # Parse store URI
        self._store = self._create_store(store)

        # Initialize components
        self.checkpoint = Checkpoint(store=self._store)
        self.detector = AnomalyDetector(
            max_loops=max_loops,
            timeout_seconds=timeout,
            cost_threshold=cost_limit / 10,  # Per-action threshold
            on_anomaly=self._on_anomaly,
        )
        self.recovery = RecoveryEngine(
            RecoveryConfig(max_retries=max_retries)
        )

        # Config
        self.cost_limit = cost_limit
        self.auto_recover = auto_recover
        self.verbose = verbose

        # Stats
        self.stats = GuardStats()

        # Set as default if requested
        if set_as_default:
            _set_default_guard(self)

    def protect(
        self,
        func: Callable[..., T] | None = None,
        *,
        name: str | None = None,
        checkpoint: bool = True,
        recover: bool | None = None,
        timeout: float | None = None,
        strategy: RecoveryStrategy | None = None,
        strategies: list[RecoveryStrategy] | None = None,
    ) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
        """
        Decorator to protect a function with checkpointing and recovery.

        Args:
            func: Function to protect
            name: Custom name for tracking
            checkpoint: Whether to checkpoint before execution
            recover: Whether to auto-recover (defaults to self.auto_recover)
            timeout: Per-call timeout (seconds); a slower call is flagged as a
                TIMEOUT anomaly (detection is post-hoc — the call is not killed)
            strategy: Recovery strategy to use (defaults to EXPONENTIAL_BACKOFF)
            strategies: Optional escalation plan (one strategy per attempt),
                e.g. [RETRY, SIMPLIFY, DIFFERENT_MODEL]. Overrides `strategy`.

        Usage:
            @guard.protect
            def my_function():
                ...

            @guard.protect(strategies=[RecoveryStrategy.RETRY,
                                       RecoveryStrategy.DIFFERENT_MODEL])
            def another_function():
                ...
        """
        if recover is None:
            recover = self.auto_recover
        if strategy is None:
            strategy = RecoveryStrategy.EXPONENTIAL_BACKOFF

        def decorator(f: Callable[..., T]) -> Callable[..., T]:
            action_name = name or f.__name__

            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> T:
                return self._execute_protected(
                    f,
                    args,
                    kwargs,
                    action_name,
                    checkpoint,
                    recover,
                    strategy,
                    strategies,
                    timeout,
                )

            return wrapper

        if func is not None:
            return decorator(func)
        return decorator

    def action(
        self,
        name: str,
        state: dict[str, Any] | None = None,
        cost: float = 0.0,
    ):
        """
        Context manager for protecting a code block.

        Args:
            name: Action name for tracking
            state: Optional state to checkpoint
            cost: Cost in USD attributed to this action (for cost tracking)

        Usage:
            with guard.action("deploy", state={"version": "1.0"}):
                deploy_to_prod()
        """
        return _ActionContext(self, name, state, cost)

    def record_cost(self, cost: float) -> None:
        """
        Report the cost (USD) of an action for tracking and spike detection.

        Use this when the cost is only known after the action runs, e.g.::

            @guard.protect
            def call_llm(prompt):
                resp = llm.complete(prompt)
                guard.record_cost(resp.usage.cost)
                return resp

        Args:
            cost: Cost in USD to add to the running total.
        """
        if cost <= 0:
            return
        self.stats.total_cost += cost
        self.detector.record_cost(cost)

    def on_recover(
        self,
        strategy: RecoveryStrategy,
        callback: Callable[..., Any],
    ) -> None:
        """
        Register a callback that runs before a retry uses ``strategy``.

        This is what makes strategies like ``DIFFERENT_MODEL`` or ``SIMPLIFY``
        do real work: the callback transforms shared state (swap the model,
        shorten the prompt, ...) so the next attempt behaves differently.

        The callback may accept ``(attempt, error)``, ``(attempt,)``, or no
        arguments.

        Usage:
            guard.on_recover(RecoveryStrategy.DIFFERENT_MODEL,
                             lambda attempt, err: switch_to_fallback_model())
        """
        self.recovery.register_callback(strategy, callback)

    def save(self, name: str, state: dict[str, Any]) -> str:
        """Save a checkpoint manually."""
        checkpoint_id = self.checkpoint.save(name, state)
        self.stats.checkpoints_created += 1
        if self.verbose:
            print(f"[AgentGuard] Checkpoint saved: {name} ({checkpoint_id})")
        return checkpoint_id

    def rollback(self, checkpoint_id: str | None = None) -> dict[str, Any]:
        """Rollback to a checkpoint."""
        state = self.checkpoint.restore(checkpoint_id)
        self.stats.rollbacks_performed += 1
        if self.verbose:
            print(f"[AgentGuard] Rolled back to checkpoint: {checkpoint_id or 'latest'}")
        return state

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        return {
            "total_actions": self.stats.total_actions,
            "successful_actions": self.stats.successful_actions,
            "failed_actions": self.stats.failed_actions,
            "recovered_actions": self.stats.recovered_actions,
            "success_rate": f"{self.stats.success_rate:.1%}",
            "anomalies_detected": self.stats.anomalies_detected,
            "checkpoints_created": self.stats.checkpoints_created,
            "rollbacks_performed": self.stats.rollbacks_performed,
            "total_cost": f"${self.stats.total_cost:.4f}",
            "runtime": f"{self.stats.runtime_seconds:.1f}s",
        }

    def reset(self) -> None:
        """Reset all state."""
        self.checkpoint.clear()
        self.detector.reset()
        self.stats = GuardStats()

    def _execute_protected(
        self,
        func: Callable[..., T],
        args: tuple,
        kwargs: dict,
        name: str,
        do_checkpoint: bool,
        do_recover: bool,
        strategy: RecoveryStrategy = RecoveryStrategy.EXPONENTIAL_BACKOFF,
        strategies: list[RecoveryStrategy] | None = None,
        timeout: float | None = None,
    ) -> T:
        """Execute a function with protection."""
        self.stats.total_actions += 1

        # Checkpoint if requested
        if do_checkpoint:
            state = {"function": name, "args": str(args)[:200], "kwargs": str(kwargs)[:200]}
            self.checkpoint.save(f"before_{name}", state)
            self.stats.checkpoints_created += 1

        # Apply a per-call timeout override for anomaly detection, if given.
        prev_timeout = self.detector.timeout_seconds
        if timeout is not None:
            self.detector.timeout_seconds = timeout

        # Start tracking
        self.detector.start_action(name)

        def execute() -> T:
            return func(*args, **kwargs)

        try:
            if do_recover:
                result = self.recovery.execute_with_recovery(
                    execute,
                    strategy=strategy,
                    strategies=strategies,
                )

                # Record outcome
                self.detector.end_action(name, success=result.success)

                if result.success:
                    self.stats.successful_actions += 1
                    if result.attempts > 1:
                        self.stats.recovered_actions += 1
                    return result.final_result
                else:
                    self.stats.failed_actions += 1
                    if result.error:
                        raise result.error
                    raise RuntimeError(
                        f"Action {name} failed after {result.attempts} attempts"
                    )
            else:
                try:
                    result = execute()
                    self.detector.end_action(name, success=True)
                    self.stats.successful_actions += 1
                    return result
                except Exception:
                    self.detector.end_action(name, success=False)
                    self.stats.failed_actions += 1
                    raise
        finally:
            self.detector.timeout_seconds = prev_timeout

    def _on_anomaly(self, anomaly: Anomaly) -> None:
        """Handle detected anomaly."""
        self.stats.anomalies_detected += 1
        if self.verbose:
            print(f"[AgentGuard] Anomaly detected: {anomaly.type.name} - {anomaly.message}")

    def _create_store(self, uri: str):
        """Create store from URI."""
        if uri.startswith("sqlite:///"):
            path = uri[10:]
            return SQLiteStore(path)
        elif uri.startswith("redis://"):
            raise NotImplementedError(
                "Redis backend is not implemented yet (see roadmap). "
                "Use 'sqlite:///path.db' or 'memory' for now."
            )
        elif uri == "memory":
            from agentguard.stores.memory import MemoryStore
            return MemoryStore()
        else:
            # Default to SQLite
            return SQLiteStore(uri)


class _ActionContext:
    """Context manager for guard.action()."""

    def __init__(
        self,
        guard: AgentGuard,
        name: str,
        state: dict[str, Any] | None,
        cost: float = 0.0,
    ):
        self.guard = guard
        self.name = name
        self.state = state or {}
        self.cost = cost
        self._checkpoint_id: str | None = None

    def __enter__(self) -> _ActionContext:
        self._checkpoint_id = self.guard.save(f"before_{self.name}", self.state)
        self.guard.detector.start_action(self.name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        success = exc_type is None
        self.guard.detector.end_action(self.name, success=success, cost=self.cost)
        if self.cost > 0:
            self.guard.stats.total_cost += self.cost

        if not success:
            self.guard.stats.failed_actions += 1
            if self.guard.auto_recover and self._checkpoint_id:
                self.guard.rollback(self._checkpoint_id)
        else:
            self.guard.stats.successful_actions += 1

        self.guard.stats.total_actions += 1
        return False  # Don't suppress exceptions


def guard(
    func: Callable[..., T] | None = None,
    *,
    max_retries: int = 3,
    timeout: float = 30.0,
    checkpoint: bool = True,
) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Convenience decorator using the default guard.

    Usage:
        @guard
        def my_function():
            ...

        @guard(max_retries=5, timeout=60)
        def another_function():
            ...
    """
    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            default = _get_default_guard()
            if default is None:
                # Create a temporary guard
                temp = AgentGuard(set_as_default=False)
                return temp._execute_protected(f, args, kwargs, f.__name__, checkpoint, True)
            return default._execute_protected(f, args, kwargs, f.__name__, checkpoint, True)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
