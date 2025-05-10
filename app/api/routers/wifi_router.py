from fastapi import APIRouter, Depends, status
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
