from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db
from app.schemas.wifi_evil_twin import EvilTwinRequest, EvilTwinStatus
from app.services.wifi_evil_twin_service import WifiEvilTwinService

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.post(
    "/evil-twin/start",
    response_model=str,
    summary="Start evil twin attack on a WiFi network",
)
async def start_evil_twin(
    req: EvilTwinRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Start an Evil Twin attack. If 'interface' or 'hotspot_name' are not provided,
    use default from settings or set hotspot_name to essid.
    """
    from app.core.config import settings

    try:
        interface = req.interface or settings.alfa_interface
        hotspot_name = req.hotspot_name or req.essid
        service = WifiEvilTwinService(db)
        result = await service.start_evil_twin(str(req.channel), interface, hotspot_name)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start evil twin attack: {str(e)}",
        )


@router.post(
    "/evil-twin/stop/{bssid}",
    response_model=EvilTwinStatus,
    summary="Stop a running evil twin attack",
)
async def stop_evil_twin(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiEvilTwinService(db)
    result = await service.stop_evil_twin(bssid)
    return result


@router.get(
    "/evil-twin/stream/{bssid}",
    response_class=StreamingResponse,
    summary="Stream evil twin attack progress via SSE",
)
async def stream_evil_twin(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiEvilTwinService(db)

    return StreamingResponse(
        service.events(bssid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
