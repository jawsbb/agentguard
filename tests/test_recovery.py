"""Tests for the recovery engine."""

import pytest

from agentguard.core.detector import Anomaly, AnomalyType
from agentguard.core.recovery import (
    RecoveryConfig,
    RecoveryEngine,
    RecoveryStrategy,
    recover,
)


class TestExecuteWithRecovery:
    def test_succeeds_first_try(self):
        engine = RecoveryEngine(RecoveryConfig(max_retries=3, base_delay=0))
        result = engine.execute_with_recovery(lambda: 42)
        assert result.success is True
        assert result.attempts == 1
        assert result.final_result == 42

    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("not yet")
            return "ok"

        engine = RecoveryEngine(RecoveryConfig(max_retries=5, base_delay=0))
        result = engine.execute_with_recovery(flaky, RecoveryStrategy.RETRY)
        assert result.success is True
        assert result.attempts == 3
        assert result.final_result == "ok"

    def test_exhausts_retries_and_reports_error(self):
        def always_fail():
            raise RuntimeError("boom")

        engine = RecoveryEngine(RecoveryConfig(max_retries=2, base_delay=0))
        result = engine.execute_with_recovery(always_fail, RecoveryStrategy.RETRY)
        assert result.success is False
        assert result.attempts == 2
        assert isinstance(result.error, RuntimeError)

    def test_abort_strategy_stops_immediately(self):
        calls = {"n": 0}

        def fail():
            calls["n"] += 1
            raise ValueError("nope")

        engine = RecoveryEngine(RecoveryConfig(max_retries=5, base_delay=0))
        result = engine.execute_with_recovery(fail, RecoveryStrategy.ABORT)
        assert result.success is False
        assert calls["n"] == 1  # no retry after abort


class TestStrategySelection:
    def test_maps_anomaly_to_strategy(self):
        engine = RecoveryEngine()
        anomaly = Anomaly(type=AnomalyType.LOOP, severity=0.8, message="loop")
        strategy = engine.get_strategy_for_anomaly(anomaly)
        assert strategy is RecoveryStrategy.SIMPLIFY

    def test_unknown_anomaly_defaults_to_retry(self):
        engine = RecoveryEngine()
        anomaly = Anomaly(type=AnomalyType.HALLUCINATION, severity=0.5, message="x")
        # HALLUCINATION is mapped; use a type not in the map via monkeypatch-free path
        engine.config.strategy_map.pop(AnomalyType.HALLUCINATION, None)
        assert engine.get_strategy_for_anomaly(anomaly) is RecoveryStrategy.RETRY


class TestRecoverHelper:
    def test_recover_returns_result(self):
        assert recover(lambda: 7, max_retries=2, strategy=RecoveryStrategy.RETRY) == 7

    def test_recover_raises_after_failures(self):
        def fail():
            raise KeyError("missing")

        with pytest.raises(KeyError):
            recover(fail, max_retries=2, strategy=RecoveryStrategy.RETRY)
