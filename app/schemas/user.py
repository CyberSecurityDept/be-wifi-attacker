from pydantic import BaseModel, EmailStr
from uuid import UUID


class UserCreate(BaseModel):
    name: str
    email: EmailStr


class UserRead(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    is_active: bool

    class Config:
        json_encoders = {UUID: lambda u: str(u)}
