from datetime import datetime, timezone
from unittest.mock import patch

from app.agents.anomaly_detector_agent import detect_anomalies
from app.agents.failure_predictor_agent import predict_failure
from app.agents.maintenance_order_agent import generate_maintenance_order
from app.agents.root_cause_agent import analyse_root_cause
from app.agents.sensor_ingestion_agent import ingest_sensors

VALID_READING = {
    "temperature": 65.0,
    "vibration": 3.5,
    "pressure": 5.0,
    "current": 20.0,
    "timestamp": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
}

HIGH_TEMP_READING = {
    "temperature": 200.0,
    "vibration": 3.5,
    "pressure": 5.0,
    "current": 20.0,
    "timestamp": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
}


def _make_state(readings: list[dict], equipment_type: str = "motor") -> dict:
    return {
        "equipment_id": "EQ-001",
        "equipment_type": equipment_type,
        "raw_readings": readings,
        "clean_readings": [],
        "anomaly_events": [],
        "failure_assessment": {},
        "root_cause_report": {},
        "maintenance_order": {},
        "errors": [],
    }


class TestSensorIngestionAgent:
    def test_validates_and_normalises_clean_batch(self):
        state = _make_state([VALID_READING])
        result = ingest_sensors(state)
        assert len(result["clean_readings"]) == 1
        reading = result["clean_readings"][0]
        assert reading["temperature"] == 65.0
        assert reading["equipment_type"] == "motor"
        assert "sensor_tags" in reading
        assert len(result["errors"]) == 0

    def test_rejects_reading_with_missing_fields(self):
        incomplete = {"temperature": 65.0, "vibration": 3.5}
        state = _make_state([incomplete])
        result = ingest_sensors(state)
        assert len(result["clean_readings"]) == 0
        assert len(result["errors"]) == 1

    def test_accepts_multiple_readings_partially(self):
        state = _make_state([VALID_READING, {"bad": "data"}])
        result = ingest_sensors(state)
        assert len(result["clean_readings"]) == 1
        assert len(result["errors"]) == 1

    def test_rejects_out_of_bounds_temperature(self):
        bad = VALID_READING.copy()
        bad["temperature"] = 9999.0
        state = _make_state([bad])
        result = ingest_sensors(state)
        assert len(result["clean_readings"]) == 0

    def test_tags_with_correct_equipment_type(self):
        state = _make_state([VALID_READING], equipment_type="turbine")
        result = ingest_sensors(state)
        assert result["clean_readings"][0]["equipment_type"] == "turbine"


class TestAnomalyDetectorAgent:
    def _ingest_and_detect(self, readings: list[dict], equipment_type: str = "motor") -> dict:
        state = _make_state(readings, equipment_type)
        ingested = ingest_sensors(state)
        return detect_anomalies(ingested)

    def test_flags_high_temperature_reading(self):
        result = self._ingest_and_detect([HIGH_TEMP_READING])
        assert len(result["anomaly_events"]) >= 1
        event = result["anomaly_events"][0]
        assert "temperature" in event["flagged_sensors"]

    def test_no_anomalies_for_normal_reading(self):
        result = self._ingest_and_detect([VALID_READING] * 10)
        assert len(result["anomaly_events"]) == 0

    def test_assigns_critical_severity_for_extreme_values(self):
        extreme = VALID_READING.copy()
        extreme["temperature"] = 499.0
        result = self._ingest_and_detect([extreme] * 5)
        severities = [e["severity"] for e in result["anomaly_events"]]
        assert "critical" in severities or "high" in severities

    def test_severity_ordering_is_correct(self):
        from app.agents.anomaly_detector_agent import _merge_severity
        assert _merge_severity("critical", "high") == "critical"
        assert _merge_severity("low", "medium") == "medium"
        assert _merge_severity(None, "high") == "high"
        assert _merge_severity("low", None) == "low"

    def test_empty_readings_returns_no_anomalies(self):
        state = {**_make_state([]), "clean_readings": []}
        result = detect_anomalies(state)
        assert result["anomaly_events"] == []


class TestFailurePredictorAgent:
    def _run(self, anomaly_events: list[dict], clean_count: int = 10) -> dict:
        state = {
            **_make_state([]),
            "clean_readings": [{}] * clean_count,
            "anomaly_events": anomaly_events,
        }
        return predict_failure(state)

    def test_probability_between_0_and_100(self):
        events = [{"severity": "high", "flagged_sensors": ["temperature"]}] * 3
        result = self._run(events)
        prob = result["failure_assessment"]["failure_probability"]
        assert 0.0 <= prob <= 100.0

    def test_no_anomalies_gives_zero_probability(self):
        result = self._run([])
        assert result["failure_assessment"]["failure_probability"] == 0.0

    def test_classifies_thermal_failure_type(self):
        events = [{"severity": "critical", "flagged_sensors": ["temperature"]}] * 5
        result = self._run(events)
        assert result["failure_assessment"]["failure_type"] == "thermal"

    def test_classifies_electrical_failure_type(self):
        events = [{"severity": "high", "flagged_sensors": ["current"]}] * 5
        result = self._run(events)
        assert result["failure_assessment"]["failure_type"] == "electrical"

    def test_high_severity_increases_probability(self):
        low_events = [{"severity": "low", "flagged_sensors": ["temperature"]}] * 3
        high_events = [{"severity": "critical", "flagged_sensors": ["temperature"]}] * 3
        low_result = self._run(low_events)
        high_result = self._run(high_events)
        assert high_result["failure_assessment"]["failure_probability"] > low_result["failure_assessment"]["failure_probability"]

    def test_ttf_is_none_for_no_anomalies(self):
        result = self._run([])
        assert result["failure_assessment"]["time_to_failure_hours"] is None


class TestRootCauseAgent:
    def _make_full_state(self, probability: float = 80.0, failure_type: str = "thermal") -> dict:
        state = _make_state([], "motor")
        state["anomaly_events"] = [{"severity": "high", "flagged_sensors": ["temperature"], "timestamp": "2024-01-01T00:00:00+00:00", "values": {}}]
        state["failure_assessment"] = {
            "failure_probability": probability,
            "failure_type": failure_type,
            "time_to_failure_hours": 12.0,
            "anomaly_count": 1,
        }
        return state

    def test_deterministic_fallback_when_groq_unavailable(self):
        state = self._make_full_state()
        with patch("app.agents.root_cause_agent.call_groq", return_value=None):
            result = analyse_root_cause(state)
        report = result["root_cause_report"]
        assert "root_cause" in report
        assert 0.0 <= report["confidence"] <= 1.0
        assert isinstance(report["contributing_factors"], list)

    def test_groq_response_used_when_valid(self):
        groq_data = {
            "root_cause": "Bearing overheating due to insufficient lubrication",
            "confidence": 0.87,
            "contributing_factors": ["Low oil level", "High ambient temperature"],
            "recommended_investigation": "Inspect bearings and oil reservoir",
        }
        state = self._make_full_state()
        with patch("app.agents.root_cause_agent.call_groq", return_value=groq_data):
            result = analyse_root_cause(state)
        report = result["root_cause_report"]
        assert report["root_cause"] == groq_data["root_cause"]
        assert report["confidence"] == 0.87

    def test_invalid_groq_response_falls_back(self):
        bad_response = {"root_cause": "Something", "confidence": "not_a_float"}
        state = self._make_full_state()
        with patch("app.agents.root_cause_agent.call_groq", return_value=bad_response):
            result = analyse_root_cause(state)
        report = result["root_cause_report"]
        assert "root_cause" in report

    def test_confidence_out_of_range_triggers_fallback(self):
        bad_response = {
            "root_cause": "Test",
            "confidence": 1.5,
            "contributing_factors": [],
            "recommended_investigation": "Inspect",
        }
        state = self._make_full_state()
        with patch("app.agents.root_cause_agent.call_groq", return_value=bad_response):
            result = analyse_root_cause(state)
        assert 0.0 <= result["root_cause_report"]["confidence"] <= 1.0


class TestMaintenanceOrderAgent:
    def _run(self, probability: float, failure_type: str = "mechanical") -> dict:
        state = {
            **_make_state([]),
            "failure_assessment": {
                "failure_probability": probability,
                "failure_type": failure_type,
                "time_to_failure_hours": 10.0,
            },
            "root_cause_report": {
                "root_cause": "Bearing wear detected",
                "confidence": 0.75,
                "recommended_investigation": "Inspect bearings",
            },
        }
        return generate_maintenance_order(state)

    def test_emergency_priority_for_critical_probability(self):
        result = self._run(90.0)
        assert result["maintenance_order"]["priority"] == "emergency"

    def test_urgent_priority_for_high_probability(self):
        result = self._run(70.0)
        assert result["maintenance_order"]["priority"] == "urgent"

    def test_scheduled_priority_for_medium_probability(self):
        result = self._run(45.0)
        assert result["maintenance_order"]["priority"] == "scheduled"

    def test_preventive_priority_for_low_probability(self):
        result = self._run(10.0)
        assert result["maintenance_order"]["priority"] == "preventive"

    def test_maintenance_order_contains_required_fields(self):
        result = self._run(50.0)
        order = result["maintenance_order"]
        for key in ["priority", "recommended_actions", "maintenance_window", "root_cause"]:
            assert key in order

    def test_recommended_actions_is_nonempty_list(self):
        result = self._run(60.0)
        actions = result["maintenance_order"]["recommended_actions"]
        assert isinstance(actions, list)
        assert len(actions) > 0
