"""Generate 500 synthetic sensor readings across five equipment types."""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

EQUIPMENT_TYPES = ["motor", "pump", "compressor", "conveyor", "turbine"]

NORMAL_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "motor": {"temperature": (40.0, 75.0), "vibration": (1.0, 5.0), "pressure": (2.0, 8.0), "current": (10.0, 40.0)},
    "pump": {"temperature": (35.0, 70.0), "vibration": (0.5, 4.5), "pressure": (3.0, 12.0), "current": (5.0, 30.0)},
    "compressor": {"temperature": (45.0, 90.0), "vibration": (1.5, 6.5), "pressure": (8.0, 25.0), "current": (15.0, 55.0)},
    "conveyor": {"temperature": (25.0, 60.0), "vibration": (0.5, 3.5), "pressure": (0.5, 4.0), "current": (3.0, 22.0)},
    "turbine": {"temperature": (60.0, 130.0), "vibration": (2.0, 8.0), "pressure": (15.0, 45.0), "current": (20.0, 90.0)},
}

ANOMALY_MULTIPLIERS: dict[str, tuple[float, float]] = {
    "temperature": (1.35, 1.7),
    "vibration": (1.8, 3.0),
    "pressure": (1.4, 2.0),
    "current": (1.3, 1.9),
}

READINGS_PER_TYPE = 100
ANOMALY_RATE = 0.15
OUTPUT_FILE = Path(__file__).parent / "sample_sensor_data.json"


def _sample_normal(lo: float, hi: float) -> float:
    mid = (lo + hi) / 2
    std = (hi - lo) / 6
    value = random.gauss(mid, std)
    return round(max(lo * 0.9, min(hi * 1.1, value)), 4)


def _sample_anomalous(lo: float, hi: float, field: str) -> float:
    lo_mul, hi_mul = ANOMALY_MULTIPLIERS[field]
    multiplier = random.uniform(lo_mul, hi_mul)
    base = random.choice([lo, hi])
    value = base * multiplier if base > 0 else hi * multiplier
    return round(value, 4)


def generate_readings() -> list[dict]:
    readings: list[dict] = []
    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    total_readings = READINGS_PER_TYPE * len(EQUIPMENT_TYPES)
    anomaly_indices = set(
        random.sample(range(total_readings), int(total_readings * ANOMALY_RATE))
    )

    global_idx = 0
    for eq_type in EQUIPMENT_TYPES:
        ranges = NORMAL_RANGES[eq_type]
        for i in range(READINGS_PER_TYPE):
            is_anomalous = global_idx in anomaly_indices
            timestamp = base_time + timedelta(minutes=global_idx * 5)

            if is_anomalous:
                anomaly_field = random.choice(list(ranges.keys()))
                reading_values: dict[str, float] = {}
                for field, (lo, hi) in ranges.items():
                    if field == anomaly_field:
                        reading_values[field] = _sample_anomalous(lo, hi, field)
                    else:
                        reading_values[field] = _sample_normal(lo, hi)
            else:
                reading_values = {field: _sample_normal(lo, hi) for field, (lo, hi) in ranges.items()}

            readings.append(
                {
                    "equipment_id": f"{eq_type.upper()}-{i + 1:03d}",
                    "equipment_type": eq_type,
                    "temperature": reading_values["temperature"],
                    "vibration": reading_values["vibration"],
                    "pressure": reading_values["pressure"],
                    "current": reading_values["current"],
                    "timestamp": timestamp.isoformat(),
                    "is_anomalous": is_anomalous,
                }
            )
            global_idx += 1

    return readings


def main() -> None:
    random.seed(42)
    readings = generate_readings()

    anomalous_count = sum(1 for r in readings if r["is_anomalous"])
    print(f"Generated {len(readings)} readings ({anomalous_count} anomalous, {anomalous_count / len(readings):.1%})")

    OUTPUT_FILE.write_text(json.dumps(readings, indent=2))
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
