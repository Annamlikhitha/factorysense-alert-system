from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import List, Optional, Union

class TelemetryBase(BaseModel):
    device_id: Union[str, int]
    timestamp: datetime
    temperature_c: float
    vibration_g: float

    @field_validator('device_id', mode='before')
    @classmethod
    def ensure_string_id(cls, v):
        return str(v)

class TelemetryInput(TelemetryBase):
    pass

class TelemetryCreate(TelemetryBase):
    pass

class Telemetry(TelemetryBase):
    id: int

    class Config:
        from_attributes = True

class DeviceStatus(BaseModel):
    device_id: str
    alert_temp_active: bool
    alert_vib_active: bool
    alert_silent_active: bool
    recent_readings: List[Telemetry]

    class Config:
        from_attributes = True
