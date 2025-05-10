import subprocess
import csv
import os
import tempfile
import shutil
from typing import List

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.helpers.network import enable_monitor, disable_monitor
from app.schemas.wifi_network import WifiNetworkCreate, WifiNetworkRead
from app.repositories.wifi_network_repository import WifiNetworkRepository

_in_progress_scans: dict[str, dict] = {}


class WifiScanService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.repo = WifiNetworkRepository(db)

    def start_scan(self, interface: str):
        info = _in_progress_scans.get(interface)
        if info:
            proc = info["process"]
            if proc.poll() is not None:
                disable_monitor(interface)
                shutil.rmtree(info["tmpdir"], ignore_errors=True)
                del _in_progress_scans[interface]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Scan already running on {interface}",
                )

        enable_monitor(interface)
        tmpdir = tempfile.mkdtemp()
        prefix = os.path.join(tmpdir, "scan")
        proc = subprocess.Popen(
            ["airodump-ng", "-w", prefix, "--output-format", "csv", interface],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _in_progress_scans[interface] = {
            "process": proc,
            "csv_path": f"{prefix}-01.csv",
            "tmpdir": tmpdir,
            "seen": set(),
        }

    def is_scanning(self, interface: str) -> bool:
        return interface in _in_progress_scans

    async def get_new_entries(self, interface: str) -> List[WifiNetworkRead]:
        info = _in_progress_scans.get(interface)
        if not info:
            return []

        path = info["csv_path"]
        if not os.path.exists(path):
            return []

        parsed = self._parse_csv(path)
        new_rows: List[WifiNetworkRead] = []
        for r in parsed:
            key = f"{r.bssid}|{r.essid}"
            if key in info["seen"]:
                continue
            info["seen"].add(key)
            created = await self.repo.create(r)
            new_rows.append(created)
        return new_rows

    async def stop_scan(self, interface: str) -> List[WifiNetworkRead]:
        info = _in_progress_scans.get(interface)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No scan in progress on {interface}",
            )

        proc = info["process"]
        proc.terminate()
        proc.wait()

        path = info["csv_path"]
        if not os.path.exists(path):
            disable_monitor(interface)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CSV output not found after stopping scan",
            )

        final = self._parse_csv(path)
        out: List[WifiNetworkRead] = []
        for r in final:
            key = f"{r.bssid}|{r.essid}"
            if key in info["seen"]:
                continue
            created = await self.repo.create(r)
            out.append(created)

        shutil.rmtree(info["tmpdir"], ignore_errors=True)
        del _in_progress_scans[interface]
        disable_monitor(interface)
        return out

    def _parse_csv(self, csv_path: str) -> List[WifiNetworkCreate]:
        networks: List[WifiNetworkCreate] = []
        with open(csv_path, newline="", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)

            for row in reader:
                if row and row[0].strip().lower() == "bssid":
                    break

            for row in reader:
                if not row or row[0] == "":
                    break

                bssid = row[0].strip()
                first_seen = row[1].strip()
                last_seen = row[2].strip()
                channel = int(row[3].strip())
                speed = int(row[4].strip())
                privacy = row[5].strip()
                cipher = row[6].strip()
                auth = row[7].strip()
                power = int(row[8].strip())
                beacons = int(row[9].strip())
                iv = int(row[10].strip())
                lan_ip = row[11].strip()
                id_length = int(row[12].strip())
                essid = row[13].strip()
                key = row[14].strip()

                networks.append(
                    WifiNetworkCreate(
                        bssid=bssid,
                        first_seen=first_seen,
                        last_seen=last_seen,
                        channel=channel,
                        speed=speed,
                        privacy=privacy,
                        cipher=cipher,
                        auth=auth,
                        power=power,
                        beacons=beacons,
                        iv=iv,
                        lan_ip=lan_ip,
                        id_length=id_length,
                        essid=essid,
                        key=key,
                        status="Main",
                    )
                )
        return networks
