from typing import Optional
from pydantic import BaseModel


class DeauthRequest(BaseModel):
    bssid: str
    essid: str
    channel: int
    interface: str


class DeauthStatus(BaseModel):
    status: str  # 'running', 'completed', 'not_found', 'stopped'
    elapsed: Optional[int] = None
    message: Optional[str] = None
