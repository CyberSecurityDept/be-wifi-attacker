from typing import Optional
from pydantic import BaseModel


class EvilTwinRequest(BaseModel):
    """
    Request schema for starting an Evil Twin attack.
    - 'essid' and 'channel' are required.
    - 'interface' and 'hotspot_name' are optional (default from settings or derived).
    """
    essid: str
    channel: int
    interface: Optional[str] = None
    hotspot_name: Optional[str] = None


class EvilTwinStatus(BaseModel):
    status: str
    elapsed: Optional[int] = None
    message: Optional[str] = None
