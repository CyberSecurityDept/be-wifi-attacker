from typing import Optional
from pydantic import BaseModel


class EvilTwinRequest(BaseModel):
    channel: int
    interface: str
    hotspot_name: str


class EvilTwinStatus(BaseModel):
    status: str
    elapsed: Optional[int] = None
    message: Optional[str] = None
