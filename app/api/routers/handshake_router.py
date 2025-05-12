from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db
from app.schemas.handshake import HandshakeRequest
from app.repositories.wifi_network_repository import WifiNetworkRepository
from app.services.wifi_handshake_service import WifiHandshakeService

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.get(
    "/handshake/stream",
    response_class=StreamingResponse,
    summary="SSE 0–100% progress; saves capture in /captures",
)
async def handshake_stream(
    bssid: str = Query(...),
    essid: str = Query(...),
    channel: int = Query(...),
    interface: str = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    repo = WifiNetworkRepository(db)
    req = HandshakeRequest(bssid=bssid, essid=essid, channel=channel, interface=interface)
    svc = WifiHandshakeService(req, repo)

    return StreamingResponse(
        svc.events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/handshake/capture",
    response_class=StreamingResponse,
    summary="SSE WPA2 handshake capture; waits until handshake is detected by aircrack-ng",
)
async def handshake_capture(
    bssid: str = Query(...),
    essid: str = Query(...),
    channel: int = Query(...),
    interface: str = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    repo = WifiNetworkRepository(db)
    req = HandshakeRequest(bssid=bssid, essid=essid, channel=channel, interface=interface)
    svc = WifiHandshakeService(req, repo)

    return StreamingResponse(
        svc.wait_for_handshake_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
