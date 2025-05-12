from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List
import asyncio

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db
from app.services.wifi_scan_service import WifiScanService
from app.schemas.wifi_network import WifiNetworkRead

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.get(
    "/scan/stream",
    response_class=StreamingResponse,
    summary="Start scan (clears old data) and stream via SSE",
)
async def stream_scan(
    interface: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiScanService(db)
    await service.repo.clear_all()
    service.start_scan(interface)

    async def event_generator():
        try:
            while service.is_scanning(interface):
                new_entries = await service.get_new_entries(interface)
                for entry in new_entries:
                    yield f"data: {entry.json()}\n\n"
                await asyncio.sleep(1)
        finally:
            final = await service.stop_scan(interface)
            for entry in final:
                yield f"data: {entry.json()}\n\n"
            yield "event: done\ndata: scan completed\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
        status_code=status.HTTP_200_OK,
    )


@router.get(
    "/list",
    response_model=List[WifiNetworkRead],
    summary="List all scanned WiFi networks",
)
async def list_wifi(db: AsyncIOMotorDatabase = Depends(get_db)):
    service = WifiScanService(db)
    return await service.repo.list_all()


@router.get(
    "/cracked/{id}",
    response_model=WifiNetworkRead,
    summary="Get cracked WiFi network by ID",
)
async def get_cracked_wifi_by_id(id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    service = WifiScanService(db)
    result = await service.repo.get_cracked_by_id(id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cracked WiFi network with ID {id} not found",
        )
    return result
