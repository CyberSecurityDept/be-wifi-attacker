# app/schemas/wifi_crack.py

from typing import Optional
from pydantic import BaseModel


class CrackRequest(BaseModel):
    bssid: str
    essid: str
    handshake_file: str
    dictionary_path: str


class CrackStatus(BaseModel):
    status: str  # 'running', 'completed', 'failed', 'not_found', 'stopped'
    password: Optional[str] = None
    total_keys: Optional[int] = None
    current_key: Optional[int] = None
    message: Optional[str] = None
