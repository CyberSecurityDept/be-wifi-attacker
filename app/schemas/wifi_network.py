from pydantic import BaseModel
from uuid import UUID


class WifiNetworkCreate(BaseModel):
    bssid: str
    first_seen: str
    last_seen: str
    channel: int
    speed: int
    privacy: str
    cipher: str
    auth: str
    power: int
    beacons: int
    iv: int
    lan_ip: str
    id_length: int
    essid: str
    key: str
    status: str = "Main"


class WifiNetworkRead(BaseModel):
    id: UUID
    bssid: str
    first_seen: str
    last_seen: str
    channel: int
    speed: int
    privacy: str
    cipher: str
    auth: str
    power: int
    beacons: int
    iv: int
    lan_ip: str
    id_length: int
    essid: str
    key: str
    status: str

    class Config:
        json_encoders = {UUID: lambda u: str(u)}
