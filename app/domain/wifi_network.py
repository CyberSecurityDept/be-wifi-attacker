from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass
class WifiNetwork:
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

    @classmethod
    def create(
        cls,
        bssid: str,
        first_seen: str,
        last_seen: str,
        channel: int,
        speed: int,
        privacy: str,
        cipher: str,
        auth: str,
        power: int,
        beacons: int,
        iv: int,
        lan_ip: str,
        id_length: int,
        essid: str,
        key: str,
        status: str = "Main",
    ) -> "WifiNetwork":
        return cls(
            id=uuid4(),
            bssid=bssid,
            first_seen=first_seen,
            last_seen=last_seen,
            channel=channel,
            speed=speed,
            privacy=privacy,
            cipher=cipher,
            auth=auth,
            power=power,
            beacons=beacons,
            iv=iv,
            lan_ip=lan_ip,
            id_length=id_length,
            essid=essid,
            key=key,
            status=status,
        )
