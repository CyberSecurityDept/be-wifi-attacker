from app.db.session import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_db() -> AsyncIOMotorDatabase:
    return get_database()
