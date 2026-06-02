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


class TestEscalation:
    def test_callback_runs_before_retry(self):
        engine = RecoveryEngine(RecoveryConfig(max_retries=3, base_delay=0))
        engine.register_callback(RecoveryStrategy.SIMPLIFY, lambda: switched.append(1))
        switched: list[int] = []

        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry me")
            return "ok"

        result = engine.execute_with_recovery(
            flaky, strategies=[RecoveryStrategy.SIMPLIFY]
        )
        assert result.success is True
        assert switched == [1]  # callback fired once before the 2nd attempt

    def test_escalates_through_plan(self):
        engine = RecoveryEngine(RecoveryConfig(max_retries=4, base_delay=0))
        used: list[str] = []
        engine.register_callback(
            RecoveryStrategy.SIMPLIFY, lambda a, e: used.append("simplify")
        )
        engine.register_callback(
            RecoveryStrategy.DIFFERENT_MODEL, lambda a, e: used.append("model")
        )

        def always_fail():
            raise RuntimeError("boom")

        engine.execute_with_recovery(
            always_fail,
            strategies=[
                RecoveryStrategy.RETRY,
                RecoveryStrategy.SIMPLIFY,
                RecoveryStrategy.DIFFERENT_MODEL,
            ],
        )
        # fail1 -> plan[0]=RETRY, fail2 -> plan[1]=SIMPLIFY, fail3 -> plan[2]=MODEL
        assert used == ["simplify", "model"]

    def test_callback_receives_attempt_and_error(self):
        engine = RecoveryEngine(RecoveryConfig(max_retries=2, base_delay=0))
        seen: list = []
        engine.register_callback(
            RecoveryStrategy.RETRY, lambda attempt, error: seen.append((attempt, type(error)))
        )

        def fail():
            raise KeyError("k")

        engine.execute_with_recovery(fail, RecoveryStrategy.RETRY)
        assert seen == [(1, KeyError)]

    def test_execute_for_anomaly_uses_mapped_plan(self):
        from agentguard.core.detector import Anomaly, AnomalyType

        engine = RecoveryEngine(RecoveryConfig(max_retries=3, base_delay=0))
        used: list[str] = []
        engine.register_callback(
            RecoveryStrategy.SIMPLIFY, lambda a, e: used.append("simplify")
        )

        def fail():
            raise ValueError("x")

        anomaly = Anomaly(type=AnomalyType.LOOP, severity=0.8, message="loop")
        # LOOP maps to [SIMPLIFY, ROLLBACK]
        engine.execute_for_anomaly(fail, anomaly)
        assert "simplify" in used


class TestRecoverHelper:
    def test_recover_returns_result(self):
        assert recover(lambda: 7, max_retries=2, strategy=RecoveryStrategy.RETRY) == 7

    def test_recover_raises_after_failures(self):
        def fail():
            raise KeyError("missing")

        with pytest.raises(KeyError):
            recover(fail, max_retries=2, strategy=RecoveryStrategy.RETRY)
