"""Streamlit dashboard for IoT Sensor Anomaly Intelligence."""

import json
from io import StringIO

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="IoT Sensor Anomaly Intelligence",
    layout="wide",
)

DARK_TEMPLATE = "plotly_dark"


def _sidebar() -> dict:
    st.sidebar.title("IoT Anomaly Intelligence")
    api_base = st.sidebar.text_input("API Base URL", value="http://localhost:8009")
    st.sidebar.divider()
    st.sidebar.subheader("Authentication")
    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")
    login_btn = st.sidebar.button("Login")

    if login_btn and username and password:
        try:
            resp = requests.post(
                f"{api_base}/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if resp.status_code == 200:
                st.session_state["token"] = resp.json()["access_token"]
                st.session_state["username"] = username
                st.sidebar.success("Logged in")
            else:
                st.sidebar.error("Invalid credentials")
        except requests.RequestException as err:
            st.sidebar.error(f"Connection failed: {err}")

    st.sidebar.divider()
    st.sidebar.subheader("Groq API Key")
    groq_key = st.sidebar.text_input("Groq API Key (optional)", type="password")
    st.sidebar.caption("Key is used only for this session and is never stored.")

    if "token" in st.session_state:
        st.sidebar.success(f"Signed in as {st.session_state.get('username', '')}")

    return {"api_base": api_base, "groq_key": groq_key}


def _auth_headers(groq_key: str = "") -> dict:
    token = st.session_state.get("token", "")
    headers = {"Authorization": f"Bearer {token}"}
    if groq_key:
        headers["X-Groq-Key"] = groq_key
    return headers


def _require_auth() -> bool:
    if "token" not in st.session_state:
        st.warning("Please login using the sidebar.")
        return False
    return True


def page_analyse(api_base: str, groq_key: str) -> None:
    st.title("Analyse Equipment")
    if not _require_auth():
        return

    headers = _auth_headers(groq_key)

    with st.expander("Register New Equipment", expanded=False):
        with st.form("register_equipment"):
            eq_id = st.text_input("Equipment ID (e.g. MOTOR-001)")
            eq_type = st.selectbox("Equipment Type", ["motor", "pump", "compressor", "conveyor", "turbine"])
            location = st.text_input("Location")
            submitted = st.form_submit_button("Register")
        if submitted:
            if not eq_id or not location:
                st.error("Equipment ID and location are required.")
            else:
                try:
                    resp = requests.post(
                        f"{api_base}/equipment",
                        json={"equipment_id": eq_id, "equipment_type": eq_type, "location": location},
                        headers=headers,
                        timeout=10,
                    )
                    if resp.status_code == 201:
                        st.success(f"Equipment {eq_id} registered.")
                    elif resp.status_code == 409:
                        st.warning("Equipment ID already registered.")
                    else:
                        st.error(f"Error: {resp.text}")
                except requests.RequestException as err:
                    st.error(f"Request failed: {err}")

    st.subheader("Submit Sensor Readings for Analysis")

    try:
        eq_resp = requests.get(f"{api_base}/equipment", headers=headers, timeout=10)
        equipment_list = eq_resp.json() if eq_resp.status_code == 200 else []
    except requests.RequestException:
        equipment_list = []

    if not equipment_list:
        st.info("No equipment registered yet. Register equipment above first.")
        return

    eq_options = {f"{e['equipment_id']} ({e['equipment_type']})": e["id"] for e in equipment_list}
    selected_label = st.selectbox("Select Equipment", list(eq_options.keys()))
    selected_id = eq_options[selected_label]

    input_method = st.radio("Input Method", ["JSON", "CSV"])

    readings_data = None
    if input_method == "JSON":
        sample = json.dumps(
            [
                {"temperature": 72.5, "vibration": 4.2, "pressure": 7.1, "current": 28.0, "timestamp": "2024-01-01T10:00:00+00:00"},
                {"temperature": 85.0, "vibration": 6.8, "pressure": 9.5, "current": 35.0, "timestamp": "2024-01-01T10:05:00+00:00"},
            ],
            indent=2,
        )
        json_input = st.text_area("Paste sensor readings JSON", value=sample, height=200)
        if st.button("Run Analysis"):
            try:
                readings_data = json.loads(json_input)
            except json.JSONDecodeError as err:
                st.error(f"Invalid JSON: {err}")

    else:
        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded and st.button("Run Analysis"):
            try:
                df = pd.read_csv(StringIO(uploaded.read().decode("utf-8")))
                required = {"temperature", "vibration", "pressure", "current", "timestamp"}
                if not required.issubset(df.columns):
                    st.error(f"CSV must contain columns: {sorted(required)}")
                else:
                    readings_data = df[list(required)].to_dict(orient="records")
            except Exception as err:
                st.error(f"CSV parse error: {err}")

    if readings_data is not None:
        with st.spinner("Running multi-agent analysis..."):
            try:
                resp = requests.post(
                    f"{api_base}/equipment/{selected_id}/analyse",
                    json={"readings": readings_data},
                    headers=headers,
                    timeout=60,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    _display_analysis_result(result)
                else:
                    st.error(f"Analysis failed: {resp.text}")
            except requests.RequestException as err:
                st.error(f"Request failed: {err}")


def _display_analysis_result(result: dict) -> None:
    st.success("Analysis complete")

    col1, col2, col3, col4 = st.columns(4)
    fa = result.get("failure_assessment", {})
    order = result.get("maintenance_order", {})

    col1.metric("Failure Probability", f"{fa.get('failure_probability', 0):.1f}%")
    col2.metric("Failure Type", fa.get("failure_type") or "N/A")
    col3.metric("Time to Failure", f"{fa.get('time_to_failure_hours') or 'N/A'} hrs")
    col4.metric("Anomalies Detected", result.get("anomaly_count", 0))

    priority = order.get("priority", "preventive")
    priority_colors = {"emergency": "red", "urgent": "orange", "scheduled": "blue", "preventive": "green"}
    color = priority_colors.get(priority, "blue")
    st.markdown(f"**Maintenance Priority:** :{color}[{priority.upper()}]")

    root = result.get("root_cause_report", {})
    if root:
        st.subheader("Root Cause Analysis")
        st.write(f"**Root Cause:** {root.get('root_cause', 'N/A')}")
        st.write(f"**Confidence:** {root.get('confidence', 0):.0%}")
        factors = root.get("contributing_factors", [])
        if factors:
            st.write("**Contributing Factors:**")
            for f in factors:
                st.write(f"- {f}")

    if order:
        st.subheader("Maintenance Work Order")
        st.write(f"**Maintenance Window:** {order.get('maintenance_window', 'N/A')}")
        actions = order.get("recommended_actions", [])
        if actions:
            st.write("**Recommended Actions:**")
            for action in actions:
                st.write(f"- {action}")

    errors = result.get("errors", [])
    if errors:
        with st.expander("Processing Warnings"):
            for e in errors:
                st.warning(e)


def page_registry(api_base: str, groq_key: str) -> None:
    st.title("Equipment Registry")
    if not _require_auth():
        return

    headers = _auth_headers(groq_key)
    try:
        resp = requests.get(f"{api_base}/equipment", headers=headers, timeout=10)
        if resp.status_code != 200:
            st.error("Failed to load equipment list")
            return
        equipment = resp.json()
    except requests.RequestException as err:
        st.error(f"Connection error: {err}")
        return

    if not equipment:
        st.info("No equipment registered.")
        return

    df = pd.DataFrame(equipment)
    display_cols = ["equipment_id", "equipment_type", "location", "created_at"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols], use_container_width=True)

    st.markdown(f"**Total equipment:** {len(equipment)}")
    type_counts = df["equipment_type"].value_counts()
    fig = px.bar(
        x=type_counts.index,
        y=type_counts.values,
        labels={"x": "Type", "y": "Count"},
        title="Equipment by Type",
        template=DARK_TEMPLATE,
    )
    st.plotly_chart(fig, use_container_width=True)


def page_analytics(api_base: str, groq_key: str) -> None:
    st.title("Analytics")
    if not _require_auth():
        return

    headers = _auth_headers(groq_key)

    try:
        stats_resp = requests.get(f"{api_base}/dashboard/stats", headers=headers, timeout=10)
        stats = stats_resp.json() if stats_resp.status_code == 200 else {}
        eq_resp = requests.get(f"{api_base}/equipment", headers=headers, timeout=10)
        equipment_list = eq_resp.json() if eq_resp.status_code == 200 else []
    except requests.RequestException as err:
        st.error(f"Connection error: {err}")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Equipment", stats.get("total_equipment", 0))
    col2.metric("Total Readings", stats.get("total_readings", 0))
    col3.metric("Anomaly Rate", f"{stats.get('anomaly_rate', 0):.1%}")
    col4.metric("Total Analyses", stats.get("total_analyses", 0))

    priority_breakdown = stats.get("maintenance_priority_breakdown", {})
    if priority_breakdown:
        st.subheader("Maintenance Priority Breakdown")
        fig = px.pie(
            names=list(priority_breakdown.keys()),
            values=list(priority_breakdown.values()),
            title="Maintenance Orders by Priority",
            template=DARK_TEMPLATE,
            color_discrete_map={"emergency": "#ef4444", "urgent": "#f97316", "scheduled": "#3b82f6", "preventive": "#22c55e"},
        )
        st.plotly_chart(fig, use_container_width=True)

    if equipment_list:
        st.subheader("Sensor Readings Over Time")
        selected_eq = st.selectbox(
            "Select Equipment",
            options=[f"{e['equipment_id']} ({e['equipment_type']})" for e in equipment_list],
        )
        idx = [f"{e['equipment_id']} ({e['equipment_type']})" for e in equipment_list].index(selected_eq)
        eq_id = equipment_list[idx]["id"]

        try:
            readings_resp = requests.get(f"{api_base}/equipment/{eq_id}/readings?limit=200", headers=headers, timeout=10)
            if readings_resp.status_code == 200:
                readings = readings_resp.json()
                if readings:
                    df = pd.DataFrame(readings)
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = df.sort_values("timestamp")

                    for field in ["temperature", "vibration", "pressure", "current"]:
                        if field in df.columns:
                            fig = px.line(
                                df,
                                x="timestamp",
                                y=field,
                                color="is_anomalous",
                                title=f"{field.capitalize()} Over Time",
                                template=DARK_TEMPLATE,
                                color_discrete_map={True: "#ef4444", False: "#00d4ff"},
                            )
                            st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No readings available for this equipment.")
        except requests.RequestException as err:
            st.error(f"Failed to load readings: {err}")


def page_maintenance_hub(api_base: str, groq_key: str) -> None:
    st.title("Maintenance Hub")
    if not _require_auth():
        return

    headers = _auth_headers(groq_key)

    try:
        eq_resp = requests.get(f"{api_base}/equipment", headers=headers, timeout=10)
        equipment_list = eq_resp.json() if eq_resp.status_code == 200 else []
    except requests.RequestException as err:
        st.error(f"Connection error: {err}")
        return

    all_analyses = []
    for eq in equipment_list:
        try:
            resp = requests.get(f"{api_base}/equipment/{eq['id']}/analyses", headers=headers, timeout=10)
            if resp.status_code == 200:
                for analysis in resp.json():
                    analysis["equipment_id_label"] = eq["equipment_id"]
                    analysis["equipment_type"] = eq["equipment_type"]
                    all_analyses.append(analysis)
        except requests.RequestException:
            continue

    if not all_analyses:
        st.info("No maintenance orders found. Run an analysis to generate work orders.")
        return

    df = pd.DataFrame(all_analyses)
    df["created_at"] = pd.to_datetime(df["created_at"])

    st.subheader("Filters")
    col1, col2, col3 = st.columns(3)

    with col1:
        priority_filter = st.multiselect(
            "Priority",
            options=["emergency", "urgent", "scheduled", "preventive"],
            default=["emergency", "urgent", "scheduled", "preventive"],
        )
    with col2:
        type_filter = st.multiselect(
            "Equipment Type",
            options=sorted(df["equipment_type"].unique().tolist()),
            default=sorted(df["equipment_type"].unique().tolist()),
        )
    with col3:
        if not df.empty:
            min_date = df["created_at"].min().date()
            max_date = df["created_at"].max().date()
            date_range = st.date_input("Date Range", value=(min_date, max_date))

    filtered = df[
        df["maintenance_priority"].isin(priority_filter) & df["equipment_type"].isin(type_filter)
    ]
    if len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered["created_at"].dt.date >= start) & (filtered["created_at"].dt.date <= end)
        ]

    display_cols = ["equipment_id_label", "equipment_type", "maintenance_priority", "failure_probability", "failure_type", "maintenance_window", "created_at"]
    display_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(filtered[display_cols].sort_values("created_at", ascending=False), use_container_width=True)
    st.markdown(f"**Showing {len(filtered)} of {len(df)} work orders**")


def main() -> None:
    config = _sidebar()
    api_base = config["api_base"].rstrip("/")
    groq_key = config["groq_key"]

    pages = {
        "Analyse Equipment": page_analyse,
        "Equipment Registry": page_registry,
        "Analytics": page_analytics,
        "Maintenance Hub": page_maintenance_hub,
    }

    selected_page = st.sidebar.radio("Navigation", list(pages.keys()))
    pages[selected_page](api_base, groq_key)


if __name__ == "__main__":
    main()
