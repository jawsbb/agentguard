"""Tests for anomaly detection."""

import time

from agentguard.core.detector import AnomalyDetector, AnomalyType


class TestLoopDetection:
    def test_repeated_action_triggers_loop(self):
        detector = AnomalyDetector(max_loops=3)
        anomaly = None
        for _ in range(3):
            detector.start_action("same")
            anomaly = detector.end_action("same", success=True)
        assert anomaly is not None
        assert anomaly.type is AnomalyType.LOOP

    def test_varied_actions_do_not_loop(self):
        detector = AnomalyDetector(max_loops=3)
        result = None
        for name in ("a", "b", "c", "d"):
            detector.start_action(name)
            result = detector.end_action(name, success=True)
        assert result is None


class TestTimeout:
    def test_slow_action_triggers_timeout(self):
        detector = AnomalyDetector(timeout_seconds=0.01)
        detector.start_action("slow")
        time.sleep(0.02)
        anomaly = detector.end_action("slow", success=True)
        assert anomaly is not None
        assert anomaly.type is AnomalyType.TIMEOUT


class TestErrorCascade:
    def test_consecutive_errors_trigger_cascade(self):
        detector = AnomalyDetector(max_consecutive_errors=3)
        anomaly = None
        for _ in range(3):
            detector.start_action("flaky")
            anomaly = detector.end_action("flaky", success=False)
        assert anomaly is not None
        assert anomaly.type is AnomalyType.ERROR_CASCADE

    def test_success_resets_error_count(self):
        detector = AnomalyDetector(max_consecutive_errors=2)
        detector.start_action("x")
        detector.end_action("x", success=False)
        detector.start_action("x")
        detector.end_action("x", success=True)  # reset
        detector.start_action("x")
        anomaly = detector.end_action("x", success=False)
        assert anomaly is None  # only 1 error since reset


class TestCost:
    def test_cost_above_threshold_triggers_spike(self):
        detector = AnomalyDetector(cost_threshold=0.10)
        anomaly = detector.record_cost(0.50)
        assert anomaly is not None
        assert anomaly.type is AnomalyType.COST_SPIKE

    def test_cost_below_threshold_is_fine(self):
        detector = AnomalyDetector(cost_threshold=0.10)
        assert detector.record_cost(0.01) is None

    def test_on_anomaly_callback_fires(self):
        seen = []
        detector = AnomalyDetector(cost_threshold=0.10, on_anomaly=seen.append)
        detector.record_cost(1.0)
        assert len(seen) == 1
        assert seen[0].type is AnomalyType.COST_SPIKE


class TestOutputChecks:
    def test_low_confidence_flags_hallucination(self):
        detector = AnomalyDetector()
        anomaly = detector.check_output("nonsense", confidence=0.1)
        assert anomaly is not None
        assert anomaly.type is AnomalyType.HALLUCINATION

    def test_pattern_mismatch_flags_drift(self):
        detector = AnomalyDetector()
        anomaly = detector.check_output("hello world", expected_pattern=r"\d{3}")
        assert anomaly is not None
        assert anomaly.type is AnomalyType.DRIFT

    def test_pattern_match_is_fine(self):
        detector = AnomalyDetector()
        assert detector.check_output("code 200 ok", expected_pattern=r"\d{3}") is None
