from sqlalchemy import Column, Integer, String, Float, Boolean, Index
from .database import Base
from datetime import datetime

class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    timestamp = Column(String, index=True)
    temperature_c = Column(Float)
    vibration_g = Column(Float)

    __table_args__ = (
        Index('idx_device_timestamp', 'device_id', 'timestamp'),
    )

class DeviceState(Base):
    __tablename__ = "device_state"

    device_id = Column(String, primary_key=True, index=True)
    last_seen = Column(String)  # Using String as per DECISIONS.md (ISO-8601)
    state = Column(String, default="NORMAL")
    temp_streak = Column(Integer, default=0)
    vib_streak = Column(Integer, default=0)
    last_alert_type = Column(String, nullable=True)

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    alert_type = Column(String)
    status = Column(String)
    timestamp = Column(String)
