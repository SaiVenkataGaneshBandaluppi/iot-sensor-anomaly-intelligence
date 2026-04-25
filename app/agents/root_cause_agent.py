import logging

from app.services.groq_client import call_groq

logger = logging.getLogger(__name__)

KNOWN_FAILURE_MODES = {
    "thermal": [
        "Inadequate cooling or ventilation",
        "Bearing friction and heat buildup",
        "Overloading causing excess heat",
        "Cooling system blockage",
    ],
    "mechanical": [
        "Bearing wear or misalignment",
        "Rotor imbalance",
        "Coupling wear",
        "Resonance at operating frequency",
    ],
    "pressure": [
        "Seal or gasket failure",
        "Valve blockage or partial closure",
        "Cavitation in fluid systems",
        "Pipe obstruction or scaling",
    ],
    "electrical": [
        "Winding insulation degradation",
        "Voltage supply imbalance",
        "Overload or phase loss",
        "Loose terminal connections",
    ],
}

SYSTEM_PROMPT = (
    "You are an industrial maintenance expert. Analyse the provided anomaly and failure data "
    "and return a JSON object with keys: root_cause (string), confidence (float 0.0 to 1.0), "
    "contributing_factors (list of strings), recommended_investigation (string). "
    "Base your analysis only on the data provided. Return only valid JSON, no additional text."
)


def _build_prompt(state: dict) -> str:
    anomaly_events = state.get("anomaly_events", [])
    assessment = state.get("failure_assessment", {})
    equipment_type = state.get("equipment_type", "unknown")
    sample_anomalies = anomaly_events[:5]

    return (
        f"Equipment type: {equipment_type}\n"
        f"Failure probability: {assessment.get('failure_probability', 0):.1f}%\n"
        f"Predicted failure type: {assessment.get('failure_type', 'unknown')}\n"
        f"Estimated time to failure: {assessment.get('time_to_failure_hours', 'N/A')} hours\n"
        f"Total anomaly count: {assessment.get('anomaly_count', 0)}\n"
        f"Recent anomalies (up to 5): {sample_anomalies}\n"
    )


def _deterministic_fallback(state: dict) -> dict:
    assessment = state.get("failure_assessment", {})
    failure_type = assessment.get("failure_type") or "mechanical"
    modes = KNOWN_FAILURE_MODES.get(failure_type, KNOWN_FAILURE_MODES["mechanical"])
    probability = assessment.get("failure_probability", 0.0)

    if probability >= 75:
        confidence = 0.70
        root_cause = modes[0]
    elif probability >= 40:
        confidence = 0.55
        root_cause = modes[1] if len(modes) > 1 else modes[0]
    else:
        confidence = 0.40
        root_cause = modes[-1]

    return {
        "root_cause": root_cause,
        "confidence": confidence,
        "contributing_factors": modes[1:3],
        "recommended_investigation": f"Inspect {failure_type} components and review maintenance log.",
    }


def _validate_groq_response(data: dict) -> dict:
    required_keys = {"root_cause", "confidence", "contributing_factors", "recommended_investigation"}
    if not required_keys.issubset(data.keys()):
        raise ValueError(f"Groq response missing keys: {required_keys - data.keys()}")

    confidence = float(data["confidence"])
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence {confidence} out of range [0.0, 1.0]")

    if not isinstance(data["contributing_factors"], list):
        raise ValueError("contributing_factors must be a list")

    return {
        "root_cause": str(data["root_cause"])[:512],
        "confidence": confidence,
        "contributing_factors": [str(f)[:256] for f in data["contributing_factors"][:5]],
        "recommended_investigation": str(data["recommended_investigation"])[:512],
    }


def analyse_root_cause(state: dict) -> dict:
    prompt = _build_prompt(state)
    report: dict | None = None

    raw = call_groq(prompt, SYSTEM_PROMPT)
    if raw is not None:
        try:
            report = _validate_groq_response(raw)
            logger.info("Root cause identified via Groq: %s (confidence=%.2f)", report["root_cause"], report["confidence"])
        except (ValueError, KeyError, TypeError) as err:
            logger.warning("Invalid Groq response, falling back: %s", err)
            report = None

    if report is None:
        report = _deterministic_fallback(state)
        logger.info("Root cause identified via fallback: %s", report["root_cause"])

    return {**state, "root_cause_report": report}
