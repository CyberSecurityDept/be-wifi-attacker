from fastapi import APIRouter, HTTPException, status
from typing import List

from app.schemas.dictionary import DictionaryRead, DictionaryCreate
from app.services.dictionary_service import DictionaryService

router = APIRouter(prefix="/dictionary", tags=["dictionary"])
service = DictionaryService()


@router.get(
    "/list",
    response_model=List[DictionaryRead],
    summary="List all available dictionaries",
)
async def list_dictionaries():
    """List all available dictionaries for WiFi cracking."""
    return service.list_dictionaries()


@router.post(
    "/create",
    response_model=DictionaryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new dictionary",
)
async def create_dictionary(dict_create: DictionaryCreate):
    try:
        return service.create_dictionary(dict_create.name, dict_create.content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create dictionary: {str(e)}",
        )


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dictionary",
)
async def delete_dictionary(name: str):
    """Delete a dictionary file by name."""
    success = service.delete_dictionary(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dictionary not found: {name}",
        )
