# app/schemas/wifi_mana.py
from pydantic import BaseModel, Field


class ManaAttackRequest(BaseModel):
    interface: str = Field(..., description="Interface to use for the Rogue AP")
    channel: int = Field(..., description="Channel to use for the Rogue AP")
    essid: str = Field(..., description="ESSID of the target network")
    passphrase: str = Field("12345678", description="Dummy passphrase for the Rogue AP")
    output_file: str = Field(None, description="Output file for the handshake (default: {essid}-handshake.hccapx)")
    auto_stop: bool = Field(True, description="Auto stop attack when handshake is captured")


class ManaAttackStatus(BaseModel):
    status: str
    message: str
    handshake_file: str = None
    log_file: str = None


class ManaCrackRequest(BaseModel):
    essid: str = Field(..., description="ESSID of the target network")
    bssid: str = Field(..., description="BSSID of the target network (untuk update DB)")
    handshake_file: str = Field(..., description="Path to handshake .hccapx file")
    wordlist_file: str = Field(..., description="Path to wordlist file")


class ManaCrackResult(BaseModel):
    status: str
    message: str
    password: str = None
