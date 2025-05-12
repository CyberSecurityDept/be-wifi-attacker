import motor.motor_asyncio
import asyncio


async def normalize_bssid_collection():
    client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["wifi_db"]  # Ganti 'wifi_db' dengan nama database Anda
    col = db["wifi_networks"]
    cursor = col.find({})
    async for doc in cursor:
        bssid = doc.get("bssid")
        if bssid:
            b = bssid.replace("-", "").replace(":", "").lower()
            b_norm = ":".join([b[i : i + 2] for i in range(0, 12, 2)]).upper()  # noqa
            if bssid != b_norm:
                await col.update_one({"_id": doc["_id"]}, {"$set": {"bssid": b_norm}})
                print(f"Updated {bssid} -> {b_norm}")
    print("Done normalizing BSSID.")


async def print_all_bssid():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["wifi_db"]  # Ganti jika nama database berbeda
    col = db["wifi_networks"]
    cursor = col.find({})
    print("\n=== List BSSID di database ===")
    async for doc in cursor:
        print(
            f"BSSID: {doc.get('bssid')}, ESSID: {doc.get('essid')}, Status: {doc.get('status')}, Key: {doc.get('key')}"
        )
    print("=== END ===\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        asyncio.run(print_all_bssid())
    else:
        asyncio.run(normalize_bssid_collection())
