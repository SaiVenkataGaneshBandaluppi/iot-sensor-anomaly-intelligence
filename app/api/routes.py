import logging
import re
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AnalysisResult, Equipment, SensorReading, User
from app.services.rate_limiter import limiter
from app.services.utils import (
    create_access_token,
    decode_access_token,
    sanitize_text_input,
)
from app.services.workflow import run_analysis

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_EQUIPMENT_TYPES = {"motor", "pump", "compressor", "conveyor", "turbine"}
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def _clean_username(cls, v: str) -> str:
        v = sanitize_text_input(v, 64)
        if not re.match(r"^[a-zA-Z0-9_]{3,64}$", v):
            raise ValueError("Username must be 3-64 alphanumeric characters or underscores")
        return v

    @field_validator("email")
    @classmethod
    def _clean_email(cls, v: str) -> str:
        v = v.strip().lower()[:255]
        if not EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password too long")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class EquipmentCreate(BaseModel):
    equipment_id: str
    equipment_type: str
    location: str
    installed_at: datetime | None = None

    @field_validator("equipment_id")
    @classmethod
    def _clean_equipment_id(cls, v: str) -> str:
        v = sanitize_text_input(v, 64)
        if not re.match(r"^[a-zA-Z0-9_\-]{1,64}$", v):
            raise ValueError("equipment_id must be alphanumeric with dashes/underscores")
        return v

    @field_validator("equipment_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_EQUIPMENT_TYPES:
            raise ValueError(f"equipment_type must be one of: {sorted(VALID_EQUIPMENT_TYPES)}")
        return v

    @field_validator("location")
    @classmethod
    def _clean_location(cls, v: str) -> str:
        return sanitize_text_input(v, 128)


class SensorReadingInput(BaseModel):
    temperature: float
    vibration: float
    pressure: float
    current: float
    timestamp: datetime


class AnalyseRequest(BaseModel):
    readings: list[SensorReadingInput]

    @field_validator("readings")
    @classmethod
    def _check_readings_count(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError("At least one reading is required")
        if len(v) > 500:
            raise ValueError("Maximum 500 readings per request")
        return v


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub", "")
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from err

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def _get_owned_equipment(
    equipment_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Equipment:
    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.user_id == current_user.id,
        )
    )
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")
    return equipment


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already registered")

    hashed = pwd_context.hash(body.password)
    user = User(username=body.username, email=body.email, hashed_password=hashed)
    db.add(user)
    await db.flush()
    return {"id": user.id, "username": user.username, "email": user.email}


@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": user.id})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/equipment", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def create_equipment(
    request: Request,
    body: EquipmentCreate,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(
        select(Equipment).where(
            Equipment.equipment_id == body.equipment_id,
            Equipment.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Equipment ID already registered")

    eq = Equipment(
        user_id=current_user.id,
        equipment_id=body.equipment_id,
        equipment_type=body.equipment_type,
        location=body.location,
        installed_at=body.installed_at,
    )
    db.add(eq)
    await db.flush()
    return _equipment_dict(eq)


@router.get("/equipment")
@limiter.limit("60/minute")
async def list_equipment(
    request: Request,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(select(Equipment).where(Equipment.user_id == current_user.id))
    return [_equipment_dict(eq) for eq in result.scalars().all()]


@router.get("/equipment/{equipment_id}")
@limiter.limit("60/minute")
async def get_equipment(
    request: Request,
    equipment: Equipment = Depends(_get_owned_equipment),
) -> dict:
    return _equipment_dict(equipment)


@router.delete("/equipment/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
async def delete_equipment(
    request: Request,
    equipment: Equipment = Depends(_get_owned_equipment),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.delete(equipment)


@router.post("/equipment/{equipment_id}/analyse")
@limiter.limit("10/minute")
async def analyse_equipment(
    request: Request,
    equipment_id: str,
    body: AnalyseRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.user_id == current_user.id,
        )
    )
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")

    raw_readings = [
        {
            "temperature": r.temperature,
            "vibration": r.vibration,
            "pressure": r.pressure,
            "current": r.current,
            "timestamp": r.timestamp.isoformat(),
        }
        for r in body.readings
    ]

    try:
        workflow_result = await run_analysis(equipment.equipment_id, equipment.equipment_type, raw_readings)
    except Exception as err:
        logger.error("Workflow failed for equipment %s: %s", equipment_id, err)
        analysis = AnalysisResult(
            equipment_id=equipment.id,
            failure_probability=0.0,
            maintenance_priority="preventive",
            maintenance_actions="Analysis failed; manual inspection required.",
            status="failed",
        )
        db.add(analysis)
        await db.flush()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Analysis failed") from err

    order = workflow_result.get("maintenance_order", {})
    root = workflow_result.get("root_cause_report", {})
    fa = workflow_result.get("failure_assessment", {})
    anomalies = workflow_result.get("anomaly_events", [])

    for reading_data in workflow_result.get("clean_readings", []):
        anomaly_match = next(
            (a for a in anomalies if a.get("reading_index") == workflow_result["clean_readings"].index(reading_data)),
            None,
        )
        ts_raw = reading_data.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(timezone.utc)

        sr = SensorReading(
            equipment_id=equipment.id,
            temperature=reading_data["temperature"],
            vibration=reading_data["vibration"],
            pressure=reading_data["pressure"],
            current=reading_data["current"],
            timestamp=ts,
            is_anomalous=anomaly_match is not None,
            anomaly_severity=anomaly_match["severity"] if anomaly_match else None,
        )
        db.add(sr)

    analysis = AnalysisResult(
        equipment_id=equipment.id,
        failure_probability=fa.get("failure_probability", 0.0),
        failure_type=fa.get("failure_type"),
        time_to_failure_hours=fa.get("time_to_failure_hours"),
        root_cause=root.get("root_cause"),
        root_cause_confidence=root.get("confidence"),
        maintenance_priority=order.get("priority", "preventive"),
        maintenance_actions="\n".join(order.get("recommended_actions", [])),
        maintenance_window=order.get("maintenance_window"),
        status="completed",
    )
    db.add(analysis)
    await db.flush()

    return {
        "analysis_id": analysis.id,
        "equipment_id": equipment_id,
        "failure_assessment": fa,
        "root_cause_report": root,
        "maintenance_order": order,
        "anomaly_count": len(anomalies),
        "readings_processed": len(workflow_result.get("clean_readings", [])),
        "errors": workflow_result.get("errors", []),
    }


@router.get("/equipment/{equipment_id}/readings")
@limiter.limit("60/minute")
async def list_readings(
    request: Request,
    equipment_id: str,
    limit: int = 100,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be between 1 and 500")

    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.user_id == current_user.id,
        )
    )
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")

    readings_result = await db.execute(
        select(SensorReading)
        .where(SensorReading.equipment_id == equipment_id)
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
    )
    readings = readings_result.scalars().all()
    return [_reading_dict(r) for r in readings]


@router.get("/equipment/{equipment_id}/analyses")
@limiter.limit("60/minute")
async def list_analyses(
    request: Request,
    equipment_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.user_id == current_user.id,
        )
    )
    equipment = result.scalar_one_or_none()
    if equipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")

    analyses_result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.equipment_id == equipment_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(50)
    )
    return [_analysis_dict(a) for a in analyses_result.scalars().all()]


@router.get("/dashboard/stats")
@limiter.limit("60/minute")
async def dashboard_stats(
    request: Request,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    eq_result = await db.execute(select(Equipment).where(Equipment.user_id == current_user.id))
    equipment_list = eq_result.scalars().all()
    equipment_ids = [e.id for e in equipment_list]

    total_readings = 0
    anomalous_readings = 0
    total_analyses = 0
    priority_counts: dict[str, int] = {}

    if equipment_ids:
        r = await db.execute(
            select(func.count(SensorReading.id)).where(SensorReading.equipment_id.in_(equipment_ids))
        )
        total_readings = r.scalar() or 0

        r2 = await db.execute(
            select(func.count(SensorReading.id)).where(
                SensorReading.equipment_id.in_(equipment_ids),
                SensorReading.is_anomalous.is_(True),
            )
        )
        anomalous_readings = r2.scalar() or 0

        r3 = await db.execute(
            select(func.count(AnalysisResult.id)).where(AnalysisResult.equipment_id.in_(equipment_ids))
        )
        total_analyses = r3.scalar() or 0

        for priority in ["emergency", "urgent", "scheduled", "preventive"]:
            r4 = await db.execute(
                select(func.count(AnalysisResult.id)).where(
                    AnalysisResult.equipment_id.in_(equipment_ids),
                    AnalysisResult.maintenance_priority == priority,
                )
            )
            priority_counts[priority] = r4.scalar() or 0

    return {
        "total_equipment": len(equipment_list),
        "total_readings": total_readings,
        "anomalous_readings": anomalous_readings,
        "anomaly_rate": round(anomalous_readings / total_readings, 4) if total_readings > 0 else 0.0,
        "total_analyses": total_analyses,
        "maintenance_priority_breakdown": priority_counts,
    }


def _equipment_dict(eq: Equipment) -> dict:
    return {
        "id": eq.id,
        "equipment_id": eq.equipment_id,
        "equipment_type": eq.equipment_type,
        "location": eq.location,
        "installed_at": eq.installed_at.isoformat() if eq.installed_at else None,
        "created_at": eq.created_at.isoformat(),
    }


def _reading_dict(r: SensorReading) -> dict:
    return {
        "id": r.id,
        "temperature": r.temperature,
        "vibration": r.vibration,
        "pressure": r.pressure,
        "current": r.current,
        "timestamp": r.timestamp.isoformat(),
        "is_anomalous": r.is_anomalous,
        "anomaly_severity": r.anomaly_severity,
    }


def _analysis_dict(a: AnalysisResult) -> dict:
    return {
        "id": a.id,
        "failure_probability": a.failure_probability,
        "failure_type": a.failure_type,
        "time_to_failure_hours": a.time_to_failure_hours,
        "root_cause": a.root_cause,
        "root_cause_confidence": a.root_cause_confidence,
        "maintenance_priority": a.maintenance_priority,
        "maintenance_actions": a.maintenance_actions,
        "maintenance_window": a.maintenance_window,
        "status": a.status,
        "created_at": a.created_at.isoformat(),
    }
