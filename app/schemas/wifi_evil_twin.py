# app/schemas/wifi_evil_twin.py

from typing import Optional
from pydantic import BaseModel


class EvilTwinRequest(BaseModel):
    bssid: str
    essid: str
    channel: int
    interface: str


class EvilTwinStatus(BaseModel):
    status: str  # 'running', 'completed', 'not_found', 'stopped'
    elapsed: Optional[int] = None
    message: Optional[str] = None
