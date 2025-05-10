# app/schemas/dictionary.py

from typing import List, Optional
from pydantic import BaseModel


class DictionaryBase(BaseModel):
    name: str


class DictionaryCreate(DictionaryBase):
    content: str


class DictionaryRead(DictionaryBase):
    path: str
    word_count: int

    class Config:
        orm_mode = True


class DictionaryList(BaseModel):
    dictionaries: List[DictionaryRead]
