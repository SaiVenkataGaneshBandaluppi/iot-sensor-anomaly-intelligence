import logging

import numpy as np

logger = logging.getLogger(__name__)

THRESHOLDS: dict[str, dict[str, tuple[float, float]]] = {
    "motor": {"temperature": (20.0, 85.0), "vibration": (0.0, 7.5), "pressure": (0.5, 10.0), "current": (1.0, 50.0)},
    "pump": {"temperature": (15.0, 80.0), "vibration": (0.0, 6.0), "pressure": (1.0, 15.0), "current": (0.5, 40.0)},
    "compressor": {"temperature": (20.0, 100.0), "vibration": (0.0, 8.0), "pressure": (5.0, 30.0), "current": (2.0, 60.0)},
    "conveyor": {"temperature": (15.0, 70.0), "vibration": (0.0, 5.0), "pressure": (0.1, 5.0), "current": (0.5, 30.0)},
    "turbine": {"temperature": (30.0, 150.0), "vibration": (0.0, 10.0), "pressure": (10.0, 50.0), "current": (5.0, 100.0)},
    "unknown": {"temperature": (0.0, 200.0), "vibration": (0.0, 20.0), "pressure": (0.0, 100.0), "current": (0.0, 200.0)},
}

SEVERITY_Z_THRESHOLDS = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.5}
SEVERITY_RANGE_THRESHOLDS = {"critical": 0.5, "high": 0.8, "medium": 1.0}

SENSOR_FIELDS = ["temperature", "vibration", "pressure", "current"]


def _compute_z_scores(readings: list[dict]) -> dict[str, list[float]]:
    z_scores: dict[str, list[float]] = {}
    for field in SENSOR_FIELDS:
        values = np.array([r[field] for r in readings], dtype=float)
        std = float(np.std(values))
        mean = float(np.mean(values))
        if std < 1e-9:
            z_scores[field] = [0.0] * len(values)
        else:
            z_scores[field] = [float(abs((v - mean) / std)) for v in values]
    return z_scores


def _severity_from_z(z: float) -> str | None:
    if z >= SEVERITY_Z_THRESHOLDS["critical"]:
        return "critical"
    if z >= SEVERITY_Z_THRESHOLDS["high"]:
        return "high"
    if z >= SEVERITY_Z_THRESHOLDS["medium"]:
        return "medium"
    if z >= SEVERITY_Z_THRESHOLDS["low"]:
        return "low"
    return None


def _severity_from_range(value: float, lo: float, hi: float) -> str | None:
    span = hi - lo
    if span <= 0:
        return None
    if value < lo or value > hi:
        excess = min(abs(value - lo), abs(value - hi)) / span
        if excess >= SEVERITY_RANGE_THRESHOLDS["critical"]:
            return "critical"
        if excess >= SEVERITY_RANGE_THRESHOLDS["high"]:
            return "high"
        return "medium"
    return None


def _merge_severity(a: str | None, b: str | None) -> str | None:
    order = ["critical", "high", "medium", "low"]
    if a is None:
        return b
    if b is None:
        return a
    return a if order.index(a) <= order.index(b) else b


def detect_anomalies(state: dict) -> dict:
    clean_readings: list[dict] = state.get("clean_readings", [])
    equipment_type: str = state.get("equipment_type", "unknown")
    thresholds = THRESHOLDS.get(equipment_type, THRESHOLDS["unknown"])
    anomaly_events: list[dict] = []

    if not clean_readings:
        return {**state, "anomaly_events": anomaly_events}

    z_scores = _compute_z_scores(clean_readings)

    for idx, reading in enumerate(clean_readings):
        severity: str | None = None
        flagged_sensors: list[str] = []

        for field in SENSOR_FIELDS:
            z = z_scores[field][idx]
            z_sev = _severity_from_z(z)
            lo, hi = thresholds[field]
            range_sev = _severity_from_range(reading[field], lo, hi)
            field_sev = _merge_severity(z_sev, range_sev)
            if field_sev is not None:
                flagged_sensors.append(field)
                severity = _merge_severity(severity, field_sev)

        if severity is not None:
            anomaly_events.append(
                {
                    "reading_index": idx,
                    "timestamp": reading["timestamp"],
                    "severity": severity,
                    "flagged_sensors": flagged_sensors,
                    "values": {f: reading[f] for f in SENSOR_FIELDS},
                }
            )

    logger.info(
        "Detected %d anomalies in %d readings for equipment_type=%s",
        len(anomaly_events),
        len(clean_readings),
        equipment_type,
    )
    return {**state, "anomaly_events": anomaly_events}
