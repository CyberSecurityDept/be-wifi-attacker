import os
import subprocess
from fastapi import APIRouter, status, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db

router = APIRouter(prefix="/wifi", tags=["wifi"])


@router.post(
    "/cleanup/mdk4",
    status_code=status.HTTP_200_OK,
    summary="Force kill all mdk4 processes",
)
def force_kill_mdk4():
    try:
        kill_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "kill_mdk4.sh")
        subprocess.run(["sudo", kill_script], stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "pkill", "-9", "-f", "mdk4"], stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "killall", "-9", "mdk4"], stderr=subprocess.DEVNULL)
        return {"message": "All mdk4 processes have been terminated"}
    except Exception as e:
        return {"message": f"Error terminating mdk4 processes: {str(e)}"}


@router.post(
    "/cleanup/evil-twin",
    status_code=status.HTTP_200_OK,
    summary="Force kill all create_ap (Evil Twin) processes",
)
def force_kill_create_ap():
    try:
        subprocess.run(["sudo", "pkill", "-9", "-f", "create_ap"], stderr=subprocess.DEVNULL)
        subprocess.run(["sudo", "killall", "-9", "create_ap"], stderr=subprocess.DEVNULL)
        return {"message": "All create_ap (evil twin) processes have been terminated"}
    except Exception as e:
        return {"message": f"Error terminating create_ap processes: {str(e)}"}


@router.post(
    "/cleanup/mdk4/{bssid}",
    status_code=status.HTTP_200_OK,
    summary="Force kill mdk4 processes for specific BSSID",
)
async def force_kill_mdk4_for_bssid(bssid: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        kill_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "kill_mdk4.sh")
        subprocess.run(["sudo", kill_script, bssid], stderr=subprocess.DEVNULL)

        subprocess.run(
            ["sudo", "pkill", "-9", "-f", f"mdk4.*-B {bssid}"],
            stderr=subprocess.DEVNULL,
        )

        from app.repositories.wifi_network_repository import WifiNetworkRepository

        repo = WifiNetworkRepository(db)
        await repo.update_status(bssid, "Main")
        return {"message": f"All mdk4 processes for BSSID {bssid} have been terminated"}
    except Exception as e:
        return {"message": f"Error terminating mdk4 processes: {str(e)}"}
