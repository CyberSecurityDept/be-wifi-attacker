from typing import List
from uuid import UUID
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate, UserRead
from app.domain.user import User
from motor.motor_asyncio import AsyncIOMotorDatabase


class UserRepository(BaseRepository[UserCreate, UserRead]):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.get_collection("users")

    async def create(self, obj_in: UserCreate) -> UserRead:
        user = User.create(obj_in.name, obj_in.email)
        doc = {
            "_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "is_active": user.is_active,
        }
        await self.collection.insert_one(doc)
        return UserRead(**{"id": user.id, **doc})

    async def get_all(self) -> List[UserRead]:
        cursor = self.collection.find()
        result = []
        async for doc in cursor:
            result.append(
                UserRead(
                    **{
                        "id": UUID(doc["_id"]),
                        "name": doc["name"],
                        "email": doc["email"],
                        "is_active": doc["is_active"],
                    }
                )
            )
        return result

    async def get(self, id_: str) -> UserRead | None:
        doc = await self.collection.find_one({"_id": id_})
        if not doc:
            return None
        return UserRead(
            **{
                "id": UUID(doc["_id"]),
                "name": doc["name"],
                "email": doc["email"],
                "is_active": doc["is_active"],
            }
        )
