"""Anomaly detection for AI agents."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


class AnomalyType(Enum):
    """Types of anomalies that can be detected."""

    LOOP = auto()  # Same action repeated N times
    TIMEOUT = auto()  # Action took too long
    COST_SPIKE = auto()  # Token usage anomaly
    DRIFT = auto()  # Output diverges from expected pattern
    HALLUCINATION = auto()  # Low confidence / inconsistent output
    ERROR_CASCADE = auto()  # Multiple consecutive errors


@dataclass
class Anomaly:
    """Detected anomaly."""

    type: AnomalyType
    severity: float  # 0.0 to 1.0
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class AnomalyDetector:
    """
    Detects anomalies in agent behavior.

    Usage:
        detector = AnomalyDetector(
            max_loops=5,
            timeout_seconds=30,
            cost_threshold=0.10,
        )

        # Check for anomalies
        anomaly = detector.check_action(action_name, result, metadata)
        if anomaly:
            handle_anomaly(anomaly)
    """

    # Loop detection
    max_loops: int = 5
    loop_window: int = 10

    # Timeout
    timeout_seconds: float = 30.0

    # Cost tracking
    cost_threshold: float = 0.10  # USD per action
    cost_window: int = 10

    # Error cascade
    max_consecutive_errors: int = 3

    # Callbacks
    on_anomaly: Callable[[Anomaly], None] | None = None

    def __post_init__(self) -> None:
        self._action_history: deque[str] = deque(maxlen=self.loop_window)
        self._cost_history: deque[float] = deque(maxlen=self.cost_window)
        self._error_count: int = 0
        self._action_start_time: float | None = None

    def start_action(self, action_name: str) -> None:
        """Mark the start of an action for timeout tracking."""
        self._action_start_time = time.time()
        self._action_history.append(action_name)

    def end_action(
        self,
        action_name: str,
        success: bool = True,
        cost: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> Anomaly | None:
        """
        Check for anomalies after action completion.

        Args:
            action_name: Name of the completed action
            success: Whether the action succeeded
            cost: Cost in USD (token cost)
            metadata: Additional context

        Returns:
            Anomaly if detected, None otherwise
        """
        anomalies: list[Anomaly] = []
        metadata = metadata or {}

        # Check timeout
        if self._action_start_time:
            duration = time.time() - self._action_start_time
            if duration > self.timeout_seconds:
                anomalies.append(
                    Anomaly(
                        type=AnomalyType.TIMEOUT,
                        severity=min(1.0, duration / (self.timeout_seconds * 2)),
                        message=f"Action '{action_name}' took {duration:.1f}s (limit: {self.timeout_seconds}s)",
                        context={"duration": duration, "limit": self.timeout_seconds},
                    )
                )
            self._action_start_time = None

        # Check loop
        loop_anomaly = self._check_loop(action_name)
        if loop_anomaly:
            anomalies.append(loop_anomaly)

        # Check cost
        if cost > 0:
            self._cost_history.append(cost)
            cost_anomaly = self._check_cost(cost)
            if cost_anomaly:
                anomalies.append(cost_anomaly)

        # Check error cascade
        if success:
            self._error_count = 0
        else:
            self._error_count += 1
            if self._error_count >= self.max_consecutive_errors:
                anomalies.append(
                    Anomaly(
                        type=AnomalyType.ERROR_CASCADE,
                        severity=min(1.0, self._error_count / (self.max_consecutive_errors * 2)),
                        message=f"{self._error_count} consecutive errors detected",
                        context={"error_count": self._error_count},
                    )
                )

        # Return highest severity anomaly
        if anomalies:
            anomaly = max(anomalies, key=lambda a: a.severity)
            if self.on_anomaly:
                self.on_anomaly(anomaly)
            return anomaly

        return None

    def check_output(
        self,
        output: str,
        expected_pattern: str | None = None,
        confidence: float | None = None,
    ) -> Anomaly | None:
        """
        Check output for drift or hallucination.

        Args:
            output: The agent's output
            expected_pattern: Regex or keywords expected in output
            confidence: Model confidence score (0-1)

        Returns:
            Anomaly if detected, None otherwise
        """
        # Check confidence-based hallucination
        if confidence is not None and confidence < 0.3:
            return Anomaly(
                type=AnomalyType.HALLUCINATION,
                severity=1.0 - confidence,
                message=f"Low confidence output ({confidence:.2f})",
                context={"confidence": confidence, "output_preview": output[:200]},
            )

        # Check drift from expected pattern
        if expected_pattern:
            import re

            if not re.search(expected_pattern, output, re.IGNORECASE):
                return Anomaly(
                    type=AnomalyType.DRIFT,
                    severity=0.7,
                    message=f"Output does not match expected pattern",
                    context={"pattern": expected_pattern, "output_preview": output[:200]},
                )

        return None

    def reset(self) -> None:
        """Reset detector state."""
        self._action_history.clear()
        self._cost_history.clear()
        self._error_count = 0
        self._action_start_time = None

    def _check_loop(self, action_name: str) -> Anomaly | None:
        """Check for repeated actions (loops)."""
        if len(self._action_history) < self.max_loops:
            return None

        # Count recent occurrences
        recent = list(self._action_history)[-self.max_loops :]
        if all(a == action_name for a in recent):
            return Anomaly(
                type=AnomalyType.LOOP,
                severity=0.8,
                message=f"Action '{action_name}' repeated {self.max_loops} times",
                context={"action": action_name, "count": self.max_loops},
            )

        return None

    def _check_cost(self, cost: float) -> Anomaly | None:
        """Check for cost spikes."""
        if cost > self.cost_threshold:
            return Anomaly(
                type=AnomalyType.COST_SPIKE,
                severity=min(1.0, cost / (self.cost_threshold * 3)),
                message=f"Cost spike: ${cost:.4f} (threshold: ${self.cost_threshold:.4f})",
                context={"cost": cost, "threshold": self.cost_threshold},
            )

        # Check for anomalous increase vs average
        if len(self._cost_history) >= 3:
            avg_cost = sum(list(self._cost_history)[:-1]) / (len(self._cost_history) - 1)
            if avg_cost > 0 and cost > avg_cost * 5:
                return Anomaly(
                    type=AnomalyType.COST_SPIKE,
                    severity=0.6,
                    message=f"Cost 5x above average: ${cost:.4f} vs avg ${avg_cost:.4f}",
                    context={"cost": cost, "average": avg_cost},
                )

        return None
