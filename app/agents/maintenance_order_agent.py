import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

PRIORITY_THRESHOLDS = {
    "emergency": 85.0,
    "urgent": 60.0,
    "scheduled": 30.0,
}

REPAIR_WINDOWS = {
    "emergency": "Immediate, within 4 hours",
    "urgent": "Within 24 hours",
    "scheduled": "Within 7 days",
    "preventive": "Within 30 days",
}

ACTIONS_BY_FAILURE_TYPE: dict[str, list[str]] = {
    "thermal": [
        "Inspect and clean cooling system and air filters",
        "Measure operating temperatures at all bearing points",
        "Check coolant flow rate and temperature",
        "Verify thermal protection relay settings",
    ],
    "mechanical": [
        "Inspect bearings for wear, pitting, or abnormal noise",
        "Perform vibration spectrum analysis",
        "Check shaft alignment and coupling condition",
        "Verify lubrication levels and grease quality",
    ],
    "pressure": [
        "Inspect all seals and gaskets for leaks",
        "Check valve positions and condition",
        "Flush and inspect pipework for blockages",
        "Test pressure relief valves for correct operation",
    ],
    "electrical": [
        "Inspect motor windings for insulation resistance",
        "Verify three-phase voltage balance at terminals",
        "Torque check all terminal connections",
        "Test overload relay and protection settings",
    ],
}

DEFAULT_ACTIONS = [
    "Perform general visual inspection",
    "Check all fasteners and connections",
    "Review equipment operating history",
    "Test safety shutdowns and interlocks",
]


def _determine_priority(probability: float) -> str:
    if probability >= PRIORITY_THRESHOLDS["emergency"]:
        return "emergency"
    if probability >= PRIORITY_THRESHOLDS["urgent"]:
        return "urgent"
    if probability >= PRIORITY_THRESHOLDS["scheduled"]:
        return "scheduled"
    return "preventive"


def _build_actions(failure_type: str | None, root_cause_report: dict) -> list[str]:
    type_actions = ACTIONS_BY_FAILURE_TYPE.get(failure_type or "", DEFAULT_ACTIONS)
    investigation = root_cause_report.get("recommended_investigation", "")
    actions = list(type_actions)
    if investigation and investigation not in actions:
        actions.insert(0, investigation)
    return actions[:6]


def _maintenance_window(priority: str) -> str:
    now = datetime.now(timezone.utc)
    offsets = {
        "emergency": timedelta(hours=4),
        "urgent": timedelta(hours=24),
        "scheduled": timedelta(days=7),
        "preventive": timedelta(days=30),
    }
    target = now + offsets.get(priority, timedelta(days=30))
    return target.strftime("%Y-%m-%d %H:%M UTC")


def generate_maintenance_order(state: dict) -> dict:
    assessment = state.get("failure_assessment", {})
    root_cause_report = state.get("root_cause_report", {})
    equipment_id = state.get("equipment_id", "unknown")

    probability = assessment.get("failure_probability", 0.0)
    failure_type = assessment.get("failure_type")

    priority = _determine_priority(probability)
    actions = _build_actions(failure_type, root_cause_report)
    window = _maintenance_window(priority)

    order = {
        "equipment_id": equipment_id,
        "priority": priority,
        "failure_probability": probability,
        "failure_type": failure_type,
        "root_cause": root_cause_report.get("root_cause", "Undetermined"),
        "root_cause_confidence": root_cause_report.get("confidence", 0.0),
        "recommended_actions": actions,
        "maintenance_window": window,
        "repair_window_description": REPAIR_WINDOWS[priority],
        "time_to_failure_hours": assessment.get("time_to_failure_hours"),
    }

    logger.info(
        "Maintenance order generated: equipment=%s, priority=%s, window=%s",
        equipment_id,
        priority,
        window,
    )
    return {**state, "maintenance_order": order}
