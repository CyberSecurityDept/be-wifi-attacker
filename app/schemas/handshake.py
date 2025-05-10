from pydantic import BaseModel


class HandshakeRequest(BaseModel):
    bssid: str
    essid: str
    channel: int
    interface: str


class HandshakeResult(BaseModel):
    handshake_file: str
