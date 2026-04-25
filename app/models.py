import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    equipment: Mapped[list["Equipment"]] = relationship("Equipment", back_populates="owner", cascade="all, delete-orphan")


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    equipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    owner: Mapped["User"] = relationship("User", back_populates="equipment")
    readings: Mapped[list["SensorReading"]] = relationship("SensorReading", back_populates="equipment", cascade="all, delete-orphan")
    analyses: Mapped[list["AnalysisResult"]] = relationship("AnalysisResult", back_populates="equipment", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    equipment_id: Mapped[str] = mapped_column(String(36), ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    vibration: Mapped[float] = mapped_column(Float, nullable=False)
    pressure: Mapped[float] = mapped_column(Float, nullable=False)
    current: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    equipment: Mapped["Equipment"] = relationship("Equipment", back_populates="readings")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    equipment_id: Mapped[str] = mapped_column(String(36), ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    failure_probability: Mapped[float] = mapped_column(Float, nullable=False)
    failure_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    time_to_failure_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    maintenance_priority: Mapped[str] = mapped_column(String(16), nullable=False)
    maintenance_actions: Mapped[str] = mapped_column(Text, nullable=False)
    maintenance_window: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    equipment: Mapped["Equipment"] = relationship("Equipment", back_populates="analyses")
