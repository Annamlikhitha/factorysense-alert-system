from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from datetime import datetime, timezone

from .database import Base, engine, SessionLocal
from .schemas import TelemetryInput
from .crud import create_telemetry, get_last_50, get_or_create_device
from .alert_engine import process_reading
from .scheduler import monitor_silence
from .utils import tprint, C

# ─── Logging (for uvicorn/server-level messages only) ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ─── App lifecycle ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    tprint(f"{C.CYAN}{C.BOLD}[SYSTEM] FactorySense backend starting up...{C.RESET}")
    task = asyncio.create_task(monitor_silence())
    yield
    tprint(f"{C.CYAN}[SYSTEM] Shutting down — cancelling background tasks...{C.RESET}")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        tprint(f"{C.CYAN}[SYSTEM] Background task cancelled cleanly.{C.RESET}")


app = FastAPI(
    title="FactorySense API",
    description="IoT telemetry ingestion and alerting backend",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restrict to actual origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Create DB tables ─────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)


# ─── DB session dependency ────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", summary="Basic service health check")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/", summary="Root endpoint - Welcome message")
def root():
    return {
        "message": "Welcome to FactorySense Alert Pipeline API",
        "docs": "/docs",
        "health": "/health",
        "status": "online"
    }


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.post("/telemetry", summary="Ingest a telemetry reading from a device")
def post_telemetry(data: TelemetryInput, db: Session = Depends(get_db)):
    tprint(
        f"{C.CYAN}{C.BOLD}[API] ← Device {data.device_id} | "
        f"T={data.temperature_c}°C  V={data.vibration_g}g{C.RESET}"
    )

    create_telemetry(db, data)
    device = get_or_create_device(db, data.device_id)
    process_reading(db, device, data.temperature_c, data.vibration_g, data.timestamp)

    return {"status": "ok"}


@app.get("/devices/{device_id}/status", summary="Get last 50 readings and current state for a device")
def get_status(device_id: str, db: Session = Depends(get_db)):
    readings = get_last_50(db, device_id)
    device   = get_or_create_device(db, device_id)

    return {
        "device_id": device_id,
        "state":     device.state,
        "last_seen": device.last_seen,
        "readings": [
            {
                "temperature_c": r.temperature_c,
                "vibration_g":   r.vibration_g,
                "timestamp":     r.timestamp,
            }
            for r in readings
        ],
    }


@app.get("/devices", summary="List all known devices and their current states")
def list_devices(db: Session = Depends(get_db)):
    from models import DeviceState
    devices = db.query(DeviceState).all()
    return [
        {
            "device_id":       d.device_id,
            "state":           d.state,
            "last_seen":       d.last_seen,
            "temp_streak":     d.temp_streak,
            "vib_streak":      d.vib_streak,
            "last_alert_type": d.last_alert_type,
        }
        for d in devices
    ]


@app.get("/alerts", summary="Get recent alert history (last 50)")
def list_alerts(db: Session = Depends(get_db)):
    from models import Alert
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).limit(50).all()
    return [
        {
            "id":         a.id,
            "device_id":  a.device_id,
            "alert_type": a.alert_type,
            "status":     a.status,
            "timestamp":  a.timestamp,
        }
        for a in alerts
    ]