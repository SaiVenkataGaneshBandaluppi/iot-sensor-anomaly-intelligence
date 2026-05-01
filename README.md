# IoT Sensor Anomaly Intelligence

A production-grade multi-agent system that ingests industrial IoT sensor data, detects anomalies in real time, predicts equipment failures before they occur, identifies root causes, and generates maintenance work orders using five LangGraph agents orchestrated with FastAPI, PostgreSQL, Redis, and Streamlit.

## Author

[Bandaluppi Sai Venkata Ganesh](https://github.com/SaiVenkataGaneshBandaluppi)

## What It Does

Industrial equipment failures are expensive and disruptive. This system continuously processes sensor telemetry from motors, pumps, compressors, conveyors, and turbines through a five-stage LangGraph pipeline. Each stage runs as a dedicated agent: data ingestion and validation, statistical anomaly detection via z-score and threshold analysis, failure probability estimation, root cause identification using Groq LLM with deterministic fallback, and structured maintenance work order generation. Results are stored in PostgreSQL and surfaced through a Streamlit dashboard.

## Features

- Five-agent LangGraph pipeline with deterministic fallback when LLM is unavailable
- Z-score and threshold-based anomaly detection using scipy
- Failure probability scoring with time-to-failure estimation
- Groq-powered root cause analysis (Llama-3.3-70b) with schema validation
- Structured maintenance work orders with priority classification
- JWT authentication with BOLA prevention
- SlowAPI rate limiting on all endpoints
- Full security headers middleware
- Async FastAPI with PostgreSQL and SQLAlchemy
- Streamlit dashboard with Plotly dark-theme charts
- Docker Compose for one-command deployment
- GitHub Actions CI with coverage enforcement and security scanning

## Tech Stack

- FastAPI, LangGraph, Groq (Llama-3.3-70b)
- PostgreSQL 16, Redis 7, SQLAlchemy async
- Streamlit dashboard
- scipy for statistical anomaly detection
- Docker Compose, GitHub Actions CI
- PyJWT, bcrypt, SlowAPI

## Five Agents

1. **sensor_ingestion_agent** - validates fields, normalises units, tags readings with equipment and sensor type
2. **anomaly_detector_agent** - z-score analysis and threshold checks, severity classification
3. **failure_predictor_agent** - rolling anomaly pattern analysis, failure probability and time-to-failure estimate
4. **root_cause_agent** - Groq LLM analysis with deterministic fallback, structured confidence-scored report
5. **maintenance_order_agent** - priority-based work order generation with recommended actions

## Prerequisites

- Python 3.11+
- Docker and Docker Compose (for full deployment)
- PostgreSQL 16 (or use Docker)
- Redis 7 (or use Docker)
- Groq API key (optional, system works without it)

## Setup

Clone the repository and copy the environment template:

```bash
cp .env.example .env
```

Edit `.env` and set `SECRET_KEY` to a secure random string. Optionally add your `GROQ_API_KEY`.

### Docker Compose (recommended)

```bash
docker compose up -d
```

API available at `http://localhost:8009`, dashboard at `http://localhost:8504`.

### Manual Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Start PostgreSQL and Redis, then run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8009
```

Run the dashboard:

```bash
streamlit run streamlit_app.py
```

### Generate Sample Data

```bash
python data/generate_sensor_data.py
```

## Usage

1. Register an account via `POST /auth/register`
2. Login to get a JWT via `POST /auth/login`
3. Register equipment via `POST /equipment`
4. Submit sensor readings for analysis via `POST /equipment/{id}/analyse`
5. View results in the Streamlit dashboard or via the API

Example analysis request:

```json
POST /equipment/{id}/analyse
{
  "readings": [
    {
      "temperature": 92.5,
      "vibration": 7.8,
      "pressure": 11.2,
      "current": 45.0,
      "timestamp": "2024-01-01T10:00:00+00:00"
    }
  ]
}
```

## Groq API Key

Set `GROQ_API_KEY` in your `.env` file to enable LLM-powered root cause analysis via Groq (Llama-3.3-70b). Leave it blank to run entirely on deterministic fallback logic — all five agents operate without an API key.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
coverage run -m pytest tests/ -v
coverage report
```

## License

MIT
