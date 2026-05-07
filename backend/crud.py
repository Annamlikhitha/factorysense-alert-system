from sqlalchemy.orm import Session
import models, schemas
from datetime import datetime, timezone

def create_telemetry(db: Session, telemetry: schemas.TelemetryCreate):
    db_telemetry = models.Telemetry(
        device_id=telemetry.device_id,
        timestamp=telemetry.timestamp.isoformat() if isinstance(telemetry.timestamp, datetime) else telemetry.timestamp,
        temperature_c=telemetry.temperature_c,
        vibration_g=telemetry.vibration_g
    )
    db.add(db_telemetry)
    db.commit()
    db.refresh(db_telemetry)
    return db_telemetry

def get_last_50(db: Session, device_id: str, limit: int = 50):
    return db.query(models.Telemetry)\
        .filter(models.Telemetry.device_id == device_id)\
        .order_by(models.Telemetry.timestamp.desc())\
        .limit(limit).all()

def get_or_create_device(db: Session, device_id: str):
    state = db.query(models.DeviceState).filter(models.DeviceState.device_id == device_id).first()
    if not state:
        state = models.DeviceState(
            device_id=device_id, 
            last_seen=datetime.now(timezone.utc).isoformat()
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state

def log_alert(db: Session, device_id: str, alert_type: str, status: str, timestamp: str):
    db_alert = models.Alert(
        device_id=device_id,
        alert_type=alert_type,
        status=status,
        timestamp=timestamp
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert
