from typing import Optional
from pydantic import BaseModel


class EvilTwinRequest(BaseModel):
    essid: str
    channel: int
    interface: Optional[str] = None
    hotspot_name: Optional[str] = None


class EvilTwinStatus(BaseModel):
    status: str
    elapsed: Optional[int] = None
    message: Optional[str] = None
