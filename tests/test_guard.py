"""Tests for the AgentGuard orchestrator."""

import pytest

from agentguard import AgentGuard, RecoveryStrategy


@pytest.fixture
def guard():
    # max_retries=1 keeps failure paths from sleeping on backoff.
    return AgentGuard(store="memory", max_retries=1, set_as_default=False)


class TestProtect:
    def test_successful_call_updates_stats(self, guard):
        @guard.protect
        def work():
            return "done"

        assert work() == "done"
        assert guard.stats.total_actions == 1
        assert guard.stats.successful_actions == 1
        assert guard.stats.failed_actions == 0

    def test_failure_propagates_and_counts(self, guard):
        @guard.protect
        def boom():
            raise ValueError("nope")

        with pytest.raises(ValueError):
            boom()
        assert guard.stats.failed_actions == 1

    def test_strategy_kwarg_is_accepted(self, guard):
        # Regression: the README example used protect(strategy=...).
        @guard.protect(strategy=RecoveryStrategy.RETRY)
        def work():
            return 1

        assert work() == 1

    def test_checkpoint_created_before_run(self, guard):
        @guard.protect
        def work():
            return 1

        work()
        assert guard.stats.checkpoints_created >= 1


class TestActionContext:
    def test_action_success(self, guard):
        with guard.action("deploy", state={"v": 1}):
            pass
        assert guard.stats.successful_actions == 1
        assert guard.stats.total_actions == 1

    def test_action_rolls_back_on_exception(self, guard):
        with pytest.raises(RuntimeError):
            with guard.action("deploy", state={"v": 1}):
                raise RuntimeError("fail")
        assert guard.stats.failed_actions == 1
        assert guard.stats.rollbacks_performed == 1


class TestCostTracking:
    def test_record_cost_accumulates(self, guard):
        guard.record_cost(0.02)
        guard.record_cost(0.03)
        assert guard.get_stats()["total_cost"] == "$0.0500"

    def test_action_cost_is_tracked(self, guard):
        with guard.action("call", cost=0.10):
            pass
        assert guard.stats.total_cost == pytest.approx(0.10)

    def test_cost_spike_is_detected(self, guard):
        # cost_threshold = cost_limit / 10 = 0.10 by default
        guard.record_cost(1.0)
        assert guard.stats.anomalies_detected >= 1

    def test_zero_cost_is_noop(self, guard):
        guard.record_cost(0.0)
        assert guard.stats.total_cost == 0.0


class TestRecoveryWiring:
    def test_different_model_callback_switches_then_succeeds(self, guard):
        guard.max_retries = 2
        guard.recovery.config.max_retries = 2
        guard.recovery.config.base_delay = 0  # no sleeping in tests

        state = {"model": "primary"}
        guard.on_recover(
            RecoveryStrategy.DIFFERENT_MODEL,
            lambda attempt, error: state.update(model="fallback"),
        )

        @guard.protect(strategies=[RecoveryStrategy.DIFFERENT_MODEL])
        def call():
            if state["model"] == "primary":
                raise ConnectionError("primary down")
            return "served by " + state["model"]

        assert call() == "served by fallback"
        assert guard.stats.recovered_actions == 1


class TestTimeout:
    def test_slow_call_flags_timeout_anomaly(self, guard):
        import time

        @guard.protect(timeout=0.01)
        def slow():
            time.sleep(0.02)
            return "done"

        assert slow() == "done"
        assert guard.stats.anomalies_detected >= 1

    def test_timeout_override_is_restored(self, guard):
        original = guard.detector.timeout_seconds

        @guard.protect(timeout=0.5)
        def quick():
            return 1

        quick()
        assert guard.detector.timeout_seconds == original


class TestStoreSelection:
    def test_redis_raises_clear_error(self):
        with pytest.raises(NotImplementedError):
            AgentGuard(store="redis://localhost:6379", set_as_default=False)
