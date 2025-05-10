from fastapi import APIRouter, Depends, status
from typing import List
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService
from app.api.deps import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = UserService(db)
    return await service.create_user(user_in)


@router.get("/", response_model=List[UserRead])
async def read_users(
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = UserService(db)
    return await service.list_users()
