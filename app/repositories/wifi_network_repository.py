# app/repositories/wifi_network_repository.py
from typing import List
from uuid import UUID, uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.schemas.wifi_network import WifiNetworkCreate, WifiNetworkRead


class WifiNetworkRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db.get_collection("wifi_networks")

    async def clear_all(self) -> None:
        await self.col.delete_many({})

    async def create(self, obj: WifiNetworkCreate) -> WifiNetworkRead:
        doc = obj.dict()
        id_str = str(uuid4())
        await self.col.insert_one({**doc, "_id": id_str})
        return WifiNetworkRead(
            id=UUID(id_str),
            bssid=doc["bssid"],
            first_seen=doc["first_seen"],
            last_seen=doc["last_seen"],
            channel=doc["channel"],
            speed=doc["speed"],
            privacy=doc["privacy"],
            cipher=doc["cipher"],
            auth=doc["auth"],
            power=doc["power"],
            beacons=doc["beacons"],
            iv=doc["iv"],
            lan_ip=doc["lan_ip"],
            id_length=doc["id_length"],
            essid=doc["essid"],
            key=doc["key"],
            status=doc["status"],
        )

    async def list_all(self) -> List[WifiNetworkRead]:
        out: List[WifiNetworkRead] = []
        async for d in self.col.find():
            out.append(
                WifiNetworkRead(
                    id=UUID(d["_id"]),
                    bssid=d["bssid"],
                    first_seen=d["first_seen"],
                    last_seen=d["last_seen"],
                    channel=d["channel"],
                    speed=d["speed"],
                    privacy=d["privacy"],
                    cipher=d["cipher"],
                    auth=d["auth"],
                    power=d["power"],
                    beacons=d["beacons"],
                    iv=d["iv"],
                    lan_ip=d["lan_ip"],
                    id_length=d["id_length"],
                    essid=d["essid"],
                    key=d["key"],
                    status=d.get("status", "Main"),
                )
            )
        return out

    async def update_status(self, bssid: str, status: str) -> None:
        await self.col.update_one({"bssid": bssid}, {"$set": {"status": status}})

    async def update_handshake(self, bssid: str, handshake_file: str) -> None:
        await self.col.update_one({"bssid": bssid}, {"$set": {"handshake_file": handshake_file}})

    async def update_key(self, bssid: str, key: str) -> None:
        await self.col.update_one({"bssid": bssid}, {"$set": {"key": key}})

    async def get_cracked_by_id(self, id: str) -> WifiNetworkRead:
        d = await self.col.find_one({"_id": id, "status": "Cracked"})
        if not d:
            return None

        return WifiNetworkRead(
            id=UUID(d["_id"]),
            bssid=d["bssid"],
            first_seen=d["first_seen"],
            last_seen=d["last_seen"],
            channel=d["channel"],
            speed=d["speed"],
            privacy=d["privacy"],
            cipher=d["cipher"],
            auth=d["auth"],
            power=d["power"],
            beacons=d["beacons"],
            iv=d["iv"],
            lan_ip=d["lan_ip"],
            id_length=d["id_length"],
            essid=d["essid"],
            key=d["key"],
            status=d.get("status", "Main"),
        )
