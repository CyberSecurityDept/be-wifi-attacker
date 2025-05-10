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
    """Start an evil twin attack mimicking the specified access point."""
    try:
        service = WifiEvilTwinService(db)
        bssid = await service.start_evil_twin(
            req.bssid, req.essid, str(req.channel), req.interface
        )
        return bssid
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
    """Stop a running evil twin attack."""
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
    """Stream the progress of an evil twin attack via Server-Sent Events."""
    service = WifiEvilTwinService(db)

    return StreamingResponse(
        service.events(bssid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
