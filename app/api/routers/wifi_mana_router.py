# app/api/routers/wifi_mana_router.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
import subprocess
import os

from app.api.deps import get_db
from app.schemas.wifi_mana import ManaAttackRequest, ManaAttackStatus, ManaCrackRequest, ManaCrackResult
from app.services.wifi_mana_service import WifiManaService

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.post(
    "/cleanup/hostapd-mana",
    response_model=dict,
    summary="Kill all hostapd-mana processes",
)
async def cleanup_hostapd_mana():
    """Kill all hostapd-mana processes using killall command"""
    try:
        subprocess.run(["sudo", "killall", "hostapd-mana"], check=True)
        return {"status": "success", "message": "All hostapd-mana processes killed"}
    except subprocess.CalledProcessError:
        return {"status": "success", "message": "No hostapd-mana processes found"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to kill hostapd-mana processes: {str(e)}",
        )


@router.post(
    "/mana/start",
    response_model=ManaAttackStatus,
    summary="Start hostapd-mana attack for WPA3 networks",
)
async def start_mana_attack(
    req: ManaAttackRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        service = WifiManaService(db)
        result = await service.start_mana_attack(
            req.interface,
            req.channel,
            req.essid,
            req.passphrase,
            req.output_file,
            req.auto_stop,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start mana attack: {str(e)}",
        )


@router.post(
    "/mana/crack",
    response_model=ManaCrackResult,
    summary="Crack WPA3 handshake using hashcat",
)
async def crack_mana_handshake(
    req: ManaCrackRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        service = WifiManaService(db)
        result = await service.crack_handshake(req.essid, req.bssid, req.handshake_file, req.wordlist_file)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to crack handshake: {str(e)}",
        )


@router.post(
    "/mana/crack/start",
    response_model=dict,
    summary="Start WPA3 handshake cracking (async, suitable for large dictionary)",
)
async def mana_crack_start(
    req: ManaCrackRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiManaService(db)
    return await service.start_crack(req.essid, req.bssid, req.handshake_file, req.wordlist_file)


@router.post(
    "/mana/crack/stream",
    summary="Start and stream WPA3 cracking progress/events (SSE) with single endpoint",
)
async def mana_crack_stream(
    req: ManaCrackRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiManaService(db)
    bssid = req.bssid
    job = service.get_job(bssid) if hasattr(service, "get_job") else GLOBAL_RUNNING_CRACKS.get(bssid)  # noqa
    if not job or job.get("completed"):
        await service.start_crack(req.essid, req.bssid, req.handshake_file, req.wordlist_file)
    return StreamingResponse(service.crack_stream(bssid), media_type="text/event-stream")


@router.post(
    "/mana/stop/{essid}",
    response_model=dict,
    summary="Stop a running hostapd-mana attack",
)
async def stop_mana_attack(
    essid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "scripts",
            "kill_hostapd_mana.sh",
        )
        subprocess.run([script_path], check=True)

        service = WifiManaService(db)
        try:
            result = await service.stop_mana_attack(essid)
            if result["status"] != "not_found":
                return result
        except Exception as e:
            print(f"Error in service.stop_mana_attack: {str(e)}")

        return {
            "status": "success",
            "message": f"Mana attack for {essid} stopped using kill script",
            "handshake_file": None,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop mana attack: {str(e)}",
        )


@router.get(
    "/mana/stream/{essid}",
    response_class=StreamingResponse,
    summary="Stream hostapd-mana attack progress via SSE",
)
async def stream_mana_attack(
    essid: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiManaService(db)

    return StreamingResponse(
        service.events(essid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/mana/attack",
    response_class=StreamingResponse,
    summary="Start hostapd-mana attack and stream progress in one endpoint",
)
async def start_and_stream_mana_attack(
    req: ManaAttackRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = WifiManaService(db)

    if req.essid in service._running_attacks and service._running_attacks[req.essid]["process"].poll() is None:
        return StreamingResponse(
            service.events(req.essid),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    try:
        await service.start_mana_attack(
            req.interface,
            req.channel,
            req.essid,
            req.passphrase,
            req.output_file,
            req.auto_stop,
        )
        return StreamingResponse(
            service.events(req.essid),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    except Exception as e:
        error_message = str(e)

        async def error_stream():
            yield f'event: error\ndata: {{"message":"Failed to start mana attack: {error_message}"}}\n\n'

        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
