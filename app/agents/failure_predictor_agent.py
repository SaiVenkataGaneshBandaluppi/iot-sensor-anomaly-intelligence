import logging
from collections import Counter

logger = logging.getLogger(__name__)

FAILURE_TYPE_SENSOR_MAP = {
    "thermal": ["temperature"],
    "mechanical": ["vibration"],
    "pressure": ["pressure"],
    "electrical": ["current"],
}

SEVERITY_WEIGHTS = {"critical": 4.0, "high": 2.5, "medium": 1.5, "low": 0.5}

TTF_MULTIPLIERS = {
    "critical": 2.0,
    "high": 6.0,
    "medium": 24.0,
    "low": 72.0,
}

BASE_TTF_HOURS = 168.0


def _classify_failure_type(anomaly_events: list[dict]) -> str:
    sensor_votes: Counter = Counter()
    for event in anomaly_events:
        for sensor in event.get("flagged_sensors", []):
            for ftype, sensors in FAILURE_TYPE_SENSOR_MAP.items():
                if sensor in sensors:
                    sensor_votes[ftype] += SEVERITY_WEIGHTS.get(event.get("severity", "low"), 0.5)

    if not sensor_votes:
        return "mechanical"
    return sensor_votes.most_common(1)[0][0]


def _calculate_failure_probability(anomaly_events: list[dict], total_readings: int) -> float:
    if total_readings == 0:
        return 0.0

    weighted_score = sum(SEVERITY_WEIGHTS.get(e.get("severity", "low"), 0.5) for e in anomaly_events)
    anomaly_rate = len(anomaly_events) / total_readings
    raw = (weighted_score / (total_readings * max(list(SEVERITY_WEIGHTS.values())))) * 100.0 + anomaly_rate * 30.0
    return round(min(raw, 100.0), 2)


def _estimate_ttf(anomaly_events: list[dict]) -> float | None:
    if not anomaly_events:
        return None

    severities = [e.get("severity", "low") for e in anomaly_events]
    worst = "low"
    for s in ["critical", "high", "medium", "low"]:
        if s in severities:
            worst = s
            break

    multiplier = TTF_MULTIPLIERS.get(worst, 72.0)
    count_factor = max(1.0, len(anomaly_events) / 3.0)
    return round(BASE_TTF_HOURS / (multiplier * count_factor), 1)


def predict_failure(state: dict) -> dict:
    anomaly_events: list[dict] = state.get("anomaly_events", [])
    clean_readings: list[dict] = state.get("clean_readings", [])

    probability = _calculate_failure_probability(anomaly_events, len(clean_readings))
    failure_type = _classify_failure_type(anomaly_events) if anomaly_events else None
    ttf = _estimate_ttf(anomaly_events)

    assessment = {
        "failure_probability": probability,
        "failure_type": failure_type,
        "time_to_failure_hours": ttf,
        "anomaly_count": len(anomaly_events),
        "total_readings": len(clean_readings),
    }

    logger.info(
        "Failure assessment: probability=%.1f%%, type=%s, ttf=%s hours",
        probability,
        failure_type,
        ttf,
    )
    return {**state, "failure_assessment": assessment}
