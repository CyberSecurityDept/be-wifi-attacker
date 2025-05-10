from uuid import UUID, uuid4
from dataclasses import dataclass


@dataclass
class User:
    id: UUID
    name: str
    email: str
    is_active: bool = True

    @classmethod
    def create(cls, name: str, email: str) -> "User":
        return cls(id=uuid4(), name=name, email=email)
