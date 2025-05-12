# app/services/wifi_handshake_service.py

import os
import subprocess
import asyncio
import re
from datetime import datetime

from app.helpers.network import enable_monitor, disable_monitor
from app.schemas.handshake import HandshakeRequest
from app.repositories.wifi_network_repository import WifiNetworkRepository

CAP_DIR = "captures"
TIMEOUT = 500
INTERVAL = 5


class WifiHandshakeService:
    async def wait_for_handshake_events(self, interval: int = 5):
        try:
            yield 'event: start\ndata: {"message":"Starting handshake capture"}\n\n'
            await self.start()
            yield 'event: progress\ndata: {"message":"Capture started, waiting for handshake..."}\n\n'
            max_loops = TIMEOUT // interval
            loop = 0
            while not os.path.exists(self.raw_cap) and loop < max_loops:
                yield 'event: progress\ndata: {"message":"Waiting for .cap file..."}\n\n'
                await asyncio.sleep(interval)
                loop += 1
            if not os.path.exists(self.raw_cap):
                yield 'event: error\ndata: {"message":"Timeout: .cap file not created"}\n\n'
                await self.abort()
                return

            handshake_found = False
            loop = 0
            while loop < max_loops:
                proc = await asyncio.create_subprocess_exec(
                    "aircrack-ng",
                    self.raw_cap,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await proc.communicate()
                out = stdout.decode().lower()

                handshake_count = 0
                handshake_pattern = re.search(r"wpa\s*\((\d+)\s*handshake\)", out)
                if handshake_pattern:
                    handshake_count = int(handshake_pattern.group(1))

                if handshake_count > 0:
                    yield 'event: progress\ndata: {"message":"Handshake captured!"}\n\n'
                    handshake_found = True
                    break
                else:
                    yield f'event: progress\ndata: {{"message":"No handshake yet, retrying in {interval}s..."}}\n\n'
                    await asyncio.sleep(interval)
                    loop += 1
            if handshake_found:
                await self.finalize()
                yield (f'event: done\ndata: {{"handshake_file":"{self.final_cap}"}}\n\n')
            else:
                yield 'event: error\ndata: {"message":"Timeout: no handshake detected by aircrack-ng"}\n\n'
                await self.abort()
        except Exception as e:
            yield f'event: error\ndata: {{"message":"Error during handshake capture: {str(e)}"}}\n\n'
            await self.abort()

    def __init__(self, req: HandshakeRequest, repo: WifiNetworkRepository):
        self.repo = repo
        self.bssid = req.bssid
        self.essid = req.essid.replace(" ", "_")
        self.channel = str(req.channel)
        self.iface = req.interface

        os.makedirs(CAP_DIR, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M")
        prefix = f"{ts}-{self.essid}"
        self.cap_prefix = os.path.join(CAP_DIR, prefix)
        self.raw_cap = f"{self.cap_prefix}-01.cap"
        self.final_cap = f"{self.cap_prefix}.cap"

        self.proc_airo = None

    async def start(self):
        enable_monitor(self.iface)
        await self.repo.update_status(self.bssid, "Cracking")

        self.proc_airo = subprocess.Popen(
            [
                "airodump-ng",
                "--bssid",
                self.bssid,
                "-c",
                self.channel,
                "-w",
                self.cap_prefix,
                "--output-format",
                "cap",
                self.iface,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def finalize(self):
        if self.proc_airo and self.proc_airo.poll() is None:
            self.proc_airo.kill()

        if os.path.exists(self.raw_cap):
            os.replace(self.raw_cap, self.final_cap)

        await self.repo.update_handshake(self.bssid, self.final_cap)

        disable_monitor(self.iface)

    async def abort(self):
        if self.proc_airo and self.proc_airo.poll() is None:
            self.proc_airo.kill()
        disable_monitor(self.iface)

    async def events(self):
        try:
            yield 'event: start\ndata: {"message":"Starting handshake capture"}\n\n'
            await self.start()
            yield 'event: progress\ndata: {"message":"Capture started, waiting for handshake..."}\n\n'
            max_loops = TIMEOUT // INTERVAL
            loop = 0
            while not os.path.exists(self.raw_cap) and loop < max_loops:
                yield 'event: progress\ndata: {"message":"Waiting for .cap file..."}\n\n'
                await asyncio.sleep(INTERVAL)
                loop += 1
            if not os.path.exists(self.raw_cap):
                yield 'event: error\ndata: {"message":"Timeout: .cap file not created"}\n\n'
                await self.abort()
                return

            handshake_found = False
            loop = 0
            while loop < max_loops:
                proc = await asyncio.create_subprocess_exec(
                    "aircrack-ng",
                    self.raw_cap,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await proc.communicate()
                out = stdout.decode().lower()

                handshake_count = 0
                handshake_pattern = re.search(r"wpa\s*\((\d+)\s*handshake\)", out)
                if handshake_pattern:
                    handshake_count = int(handshake_pattern.group(1))

                if handshake_count > 0:
                    yield 'event: progress\ndata: {"message":"Handshake captured!"}\n\n'
                    handshake_found = True
                    break
                else:
                    yield f'event: progress\ndata: {{"message":"No handshake yet, retrying in {INTERVAL}s..."}}\n\n'  # noqa
                    await asyncio.sleep(INTERVAL)
                    loop += 1
            if handshake_found:
                await self.finalize()
                yield (f'event: done\ndata: {{"handshake_file":"{self.final_cap}"}}\n\n')
            else:
                yield 'event: error\ndata: {"message":"Timeout: no handshake detected by aircrack-ng"}\n\n'
                await self.abort()
        except Exception as e:
            yield f'event: error\ndata: {{"message":"Failed to start handshake capture: {str(e)}"}}\n\n'
