"""Recovery strategies for failed agent actions."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, TypeVar

from agentguard.core.detector import Anomaly, AnomalyType

T = TypeVar("T")


class RecoveryStrategy(Enum):
    """Available recovery strategies."""

    RETRY = auto()  # Simple retry
    EXPONENTIAL_BACKOFF = auto()  # Retry with increasing delays
    ROLLBACK = auto()  # Restore previous checkpoint
    SIMPLIFY = auto()  # Retry with simplified prompt/context
    DIFFERENT_MODEL = auto()  # Try with a different model
    HUMAN_ESCALATE = auto()  # Pause and ask for human input
    SKIP = auto()  # Skip this action and continue
    ABORT = auto()  # Stop the workflow


@dataclass
class RecoveryConfig:
    """Configuration for recovery behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    jitter: bool = True  # Add randomness to delays

    # Strategy selection based on anomaly type
    strategy_map: dict[AnomalyType, list[RecoveryStrategy]] = field(default_factory=lambda: {
        AnomalyType.LOOP: [RecoveryStrategy.SIMPLIFY, RecoveryStrategy.ROLLBACK],
        AnomalyType.TIMEOUT: [RecoveryStrategy.RETRY, RecoveryStrategy.SKIP],
        AnomalyType.COST_SPIKE: [RecoveryStrategy.SIMPLIFY, RecoveryStrategy.DIFFERENT_MODEL],
        AnomalyType.DRIFT: [RecoveryStrategy.ROLLBACK, RecoveryStrategy.RETRY],
        AnomalyType.HALLUCINATION: [RecoveryStrategy.RETRY, RecoveryStrategy.DIFFERENT_MODEL],
        AnomalyType.ERROR_CASCADE: [RecoveryStrategy.ROLLBACK, RecoveryStrategy.HUMAN_ESCALATE],
    })


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    success: bool
    strategy_used: RecoveryStrategy
    attempts: int
    final_result: Any = None
    error: Exception | None = None
    total_time: float = 0.0


class RecoveryEngine:
    """
    Handles recovery from failures and anomalies.

    Usage:
        recovery = RecoveryEngine(config=RecoveryConfig(max_retries=3))

        result = recovery.execute_with_recovery(
            action=lambda: risky_operation(),
            on_failure=RecoveryStrategy.EXPONENTIAL_BACKOFF,
        )
    """

    def __init__(self, config: RecoveryConfig | None = None) -> None:
        self.config = config or RecoveryConfig()
        self._attempt_count: int = 0
        self._callbacks: dict[RecoveryStrategy, Callable[[], Any]] = {}

    def register_callback(
        self,
        strategy: RecoveryStrategy,
        callback: Callable[[], Any],
    ) -> None:
        """Register a callback for a specific strategy."""
        self._callbacks[strategy] = callback

    def execute_with_recovery(
        self,
        action: Callable[[], T],
        strategy: RecoveryStrategy = RecoveryStrategy.EXPONENTIAL_BACKOFF,
        on_anomaly: Callable[[Anomaly], RecoveryStrategy] | None = None,
    ) -> RecoveryResult:
        """
        Execute an action with automatic recovery.

        Args:
            action: The action to execute
            strategy: Default recovery strategy
            on_anomaly: Callback to determine strategy based on anomaly

        Returns:
            RecoveryResult with outcome details
        """
        start_time = time.time()
        self._attempt_count = 0
        last_error: Exception | None = None

        while self._attempt_count < self.config.max_retries:
            self._attempt_count += 1

            try:
                result = action()
                return RecoveryResult(
                    success=True,
                    strategy_used=strategy,
                    attempts=self._attempt_count,
                    final_result=result,
                    total_time=time.time() - start_time,
                )
            except Exception as e:
                last_error = e

                # Determine if we should continue retrying
                if self._attempt_count >= self.config.max_retries:
                    break

                # Apply recovery strategy
                should_continue = self._apply_strategy(strategy, self._attempt_count)
                if not should_continue:
                    break

        return RecoveryResult(
            success=False,
            strategy_used=strategy,
            attempts=self._attempt_count,
            error=last_error,
            total_time=time.time() - start_time,
        )

    async def execute_with_recovery_async(
        self,
        action: Callable[[], T],
        strategy: RecoveryStrategy = RecoveryStrategy.EXPONENTIAL_BACKOFF,
    ) -> RecoveryResult:
        """Async version of execute_with_recovery."""
        start_time = time.time()
        self._attempt_count = 0
        last_error: Exception | None = None

        while self._attempt_count < self.config.max_retries:
            self._attempt_count += 1

            try:
                if asyncio.iscoroutinefunction(action):
                    result = await action()
                else:
                    result = action()

                return RecoveryResult(
                    success=True,
                    strategy_used=strategy,
                    attempts=self._attempt_count,
                    final_result=result,
                    total_time=time.time() - start_time,
                )
            except Exception as e:
                last_error = e

                if self._attempt_count >= self.config.max_retries:
                    break

                delay = self._calculate_delay(strategy, self._attempt_count)
                if delay > 0:
                    await asyncio.sleep(delay)

        return RecoveryResult(
            success=False,
            strategy_used=strategy,
            attempts=self._attempt_count,
            error=last_error,
            total_time=time.time() - start_time,
        )

    def get_strategy_for_anomaly(self, anomaly: Anomaly) -> RecoveryStrategy:
        """Get the recommended recovery strategy for an anomaly."""
        strategies = self.config.strategy_map.get(anomaly.type, [RecoveryStrategy.RETRY])
        return strategies[0] if strategies else RecoveryStrategy.RETRY

    def _apply_strategy(self, strategy: RecoveryStrategy, attempt: int) -> bool:
        """
        Apply a recovery strategy.

        Returns:
            True if should retry, False if should stop
        """
        if strategy == RecoveryStrategy.ABORT:
            return False

        if strategy == RecoveryStrategy.HUMAN_ESCALATE:
            # In real implementation, this would pause and wait for human
            return False

        if strategy == RecoveryStrategy.SKIP:
            return False

        # Calculate and apply delay
        delay = self._calculate_delay(strategy, attempt)
        if delay > 0:
            time.sleep(delay)

        # Execute registered callback if any
        if strategy in self._callbacks:
            self._callbacks[strategy]()

        return True

    def _calculate_delay(self, strategy: RecoveryStrategy, attempt: int) -> float:
        """Calculate delay before next retry."""
        if strategy == RecoveryStrategy.RETRY:
            delay = self.config.base_delay
        elif strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
            delay = min(
                self.config.base_delay * (2 ** (attempt - 1)),
                self.config.max_delay,
            )
        else:
            delay = self.config.base_delay

        if self.config.jitter:
            delay *= 0.5 + random.random()

        return delay


# Convenience function for simple recovery
def recover(
    action: Callable[[], T],
    max_retries: int = 3,
    strategy: RecoveryStrategy = RecoveryStrategy.EXPONENTIAL_BACKOFF,
) -> T:
    """
    Execute an action with automatic recovery.

    Args:
        action: The action to execute
        max_retries: Maximum retry attempts
        strategy: Recovery strategy to use

    Returns:
        The action result

    Raises:
        Exception: If all retries fail
    """
    engine = RecoveryEngine(RecoveryConfig(max_retries=max_retries))
    result = engine.execute_with_recovery(action, strategy)

    if result.success:
        return result.final_result
    elif result.error:
        raise result.error
    else:
        raise RuntimeError(f"Recovery failed after {result.attempts} attempts")
