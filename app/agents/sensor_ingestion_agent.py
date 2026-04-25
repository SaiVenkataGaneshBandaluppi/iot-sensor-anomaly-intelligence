import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"temperature", "vibration", "pressure", "current", "timestamp"}

EQUIPMENT_TYPES = {"motor", "pump", "compressor", "conveyor", "turbine"}

SENSOR_TYPES = {
    "temperature": "thermal",
    "vibration": "mechanical",
    "pressure": "pressure",
    "current": "electrical",
}

FIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature": (-50.0, 500.0),
    "vibration": (0.0, 100.0),
    "pressure": (0.0, 1000.0),
    "current": (0.0, 1000.0),
}


def _parse_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    ts = str(value).strip()
    try:
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return ts
    except ValueError as err:
        raise ValueError(f"Unparseable timestamp: {value!r}") from err


def _clamp_float(value: Any, field: str) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"Field '{field}' must be numeric, got {value!r}") from err
    lo, hi = FIELD_BOUNDS[field]
    if not (lo <= f <= hi):
        raise ValueError(f"Field '{field}' value {f} is outside acceptable range [{lo}, {hi}]")
    return round(f, 6)


def _validate_reading(raw: dict) -> dict:
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    return {
        "temperature": _clamp_float(raw["temperature"], "temperature"),
        "vibration": _clamp_float(raw["vibration"], "vibration"),
        "pressure": _clamp_float(raw["pressure"], "pressure"),
        "current": _clamp_float(raw["current"], "current"),
        "timestamp": _parse_timestamp(raw["timestamp"]),
        "sensor_tags": SENSOR_TYPES.copy(),
    }


def _tag_with_equipment(reading: dict, equipment_type: str) -> dict:
    tagged = reading.copy()
    tagged["equipment_type"] = equipment_type if equipment_type in EQUIPMENT_TYPES else "unknown"
    return tagged


def ingest_sensors(state: dict) -> dict:
    raw_readings: list[dict] = state.get("raw_readings", [])
    equipment_type: str = state.get("equipment_type", "unknown")
    errors: list[str] = list(state.get("errors", []))
    clean: list[dict] = []

    for idx, raw in enumerate(raw_readings):
        try:
            validated = _validate_reading(raw)
            tagged = _tag_with_equipment(validated, equipment_type)
            clean.append(tagged)
        except ValueError as err:
            msg = f"Reading[{idx}] rejected: {err}"
            logger.warning(msg)
            errors.append(msg)

    logger.info("Ingested %d/%d readings for equipment_type=%s", len(clean), len(raw_readings), equipment_type)
    return {**state, "clean_readings": clean, "errors": errors}
