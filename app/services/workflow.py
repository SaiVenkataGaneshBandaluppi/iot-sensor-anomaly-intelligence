import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.anomaly_detector_agent import detect_anomalies
from app.agents.failure_predictor_agent import predict_failure
from app.agents.maintenance_order_agent import generate_maintenance_order
from app.agents.root_cause_agent import analyse_root_cause
from app.agents.sensor_ingestion_agent import ingest_sensors

logger = logging.getLogger(__name__)


def build_workflow() -> Any:
    graph = StateGraph(dict)
    graph.add_node("ingest_sensors", ingest_sensors)
    graph.add_node("detect_anomalies", detect_anomalies)
    graph.add_node("predict_failure", predict_failure)
    graph.add_node("analyse_root_cause", analyse_root_cause)
    graph.add_node("generate_maintenance_order", generate_maintenance_order)

    graph.add_edge(START, "ingest_sensors")
    graph.add_edge("ingest_sensors", "detect_anomalies")
    graph.add_edge("detect_anomalies", "predict_failure")
    graph.add_edge("predict_failure", "analyse_root_cause")
    graph.add_edge("analyse_root_cause", "generate_maintenance_order")
    graph.add_edge("generate_maintenance_order", END)

    return graph.compile()


_compiled_workflow = None


def get_workflow() -> Any:
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = build_workflow()
    return _compiled_workflow


async def run_analysis(equipment_id: str, equipment_type: str, readings: list[dict]) -> dict:
    workflow = get_workflow()
    initial_state: dict = {
        "equipment_id": equipment_id,
        "equipment_type": equipment_type,
        "raw_readings": readings,
        "clean_readings": [],
        "anomaly_events": [],
        "failure_assessment": {},
        "root_cause_report": {},
        "maintenance_order": {},
        "errors": [],
    }
    try:
        result = await workflow.ainvoke(initial_state)
        return result
    except Exception as err:
        logger.error("Workflow execution failed for equipment %s: %s", equipment_id, err)
        raise
