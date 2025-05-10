from typing import Generic, TypeVar, List
from abc import ABC, abstractmethod

TCreate = TypeVar("TCreate")
TRead = TypeVar("TRead")


class BaseRepository(ABC, Generic[TCreate, TRead]):
    @abstractmethod
    async def create(self, obj_in: TCreate) -> TRead: ...
    @abstractmethod
    async def get_all(self) -> List[TRead]: ...
    @abstractmethod
    async def get(self, id_: str) -> TRead | None: ...
