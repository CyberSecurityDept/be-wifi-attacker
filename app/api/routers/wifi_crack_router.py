# app/api/routers/wifi_crack_router.py

import subprocess
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db
from app.schemas.wifi_crack import CrackRequest, CrackStatus
from app.services.wifi_crack_service import WifiCrackService

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.post(
    "/crack/start",
    response_model=str,
    summary="Start WiFi password cracking using a dictionary",
)
async def start_crack(
    req: CrackRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        service = WifiCrackService(db)
        job_id = await service.start_crack(req.bssid, req.handshake_file, req.dictionary_path)
        return job_id
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start crack: {str(e)}",
        )


@router.get(
    "/crack/status/{bssid}",
    response_model=CrackStatus,
    summary="Check the status of a cracking attempt",
)
async def check_crack_status(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiCrackService(db)
    status = await service.check_crack_status(bssid)
    return status


@router.post(
    "/crack/stop/{bssid}",
    response_model=CrackStatus,
    summary="Stop a running cracking attempt",
)
async def stop_crack(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiCrackService(db)
    result = await service.stop_crack(bssid)
    return result


@router.get(
    "/crack/stream/{bssid}",
    response_class=StreamingResponse,
    summary="Stream crack progress via SSE",
)
async def stream_crack(
    bssid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiCrackService(db)

    active_cracks = WifiCrackService.get_active_cracks()
    print(f"Active cracking jobs: {active_cracks}")
    print(f"Requested BSSID: {bssid}")

    if bssid not in active_cracks:
        print(f"WARNING: BSSID {bssid} not found in active cracks list")

        try:
            output = subprocess.check_output(["pgrep", "-f", f"aircrack-ng.*-b\s+{bssid}"], text=True)  # noqa
            if output.strip():
                pid = output.strip().split("\n")[0]
                print(f"Found existing aircrack-ng process (PID: {pid}) for {bssid}, attempting to recover")
        except subprocess.CalledProcessError:
            print(f"No existing aircrack-ng process found for {bssid}")

    return StreamingResponse(
        service.events(bssid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
