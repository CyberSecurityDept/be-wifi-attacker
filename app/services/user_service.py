from typing import List
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserRead
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status


class UserService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.repo = UserRepository(db)

    async def create_user(self, data: UserCreate) -> UserRead:
        existing = await self.repo.collection.find_one({"email": data.email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        return await self.repo.create(data)

    async def list_users(self) -> List[UserRead]:
        return await self.repo.get_all()
