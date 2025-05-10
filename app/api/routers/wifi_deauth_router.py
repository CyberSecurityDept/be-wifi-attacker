from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db
from app.schemas.wifi_deauth import DeauthRequest
from app.services.wifi_deauth_service import WifiDeauthService

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.post(
    "/deauth/start",
    response_model=str,
    summary="Start deauthentication attack on a WiFi network",
)
async def start_deauth(
    req: DeauthRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        service = WifiDeauthService(db)
        bssid = await service.start_deauth(req.bssid, str(req.channel), req.interface)
        return bssid
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start deauth attack: {str(e)}",
        )


@router.post(
    "/deauth/stop/{bssid}",
    response_model=bool,
    summary="Stop a running deauthentication attack",
)
async def stop_deauth(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiDeauthService(db)
    result = await service.stop_deauth(bssid)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No deauth attack found for {bssid}",
        )
    return result


@router.get(
    "/deauth/stream/{bssid}",
    response_class=StreamingResponse,
    summary="Stream deauth attack progress via SSE",
)
async def stream_deauth(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiDeauthService(db)

    return StreamingResponse(
        service.events(bssid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
