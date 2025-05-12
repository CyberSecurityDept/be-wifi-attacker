import subprocess
import logging

logger = logging.getLogger("wifi_network")


def enable_monitor(iface: str):
    try:
        subprocess.run(["sudo", "ip", "link", "set", iface, "down"], check=True)
        subprocess.run(["sudo", "iw", iface, "set", "monitor", "none"], check=True)
        subprocess.run(["sudo", "ip", "link", "set", iface, "up"], check=True)
        logger.info(f"Successfully enabled monitor mode on {iface}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to enable monitor mode on {iface}: {str(e)}")
        return False


def disable_monitor(iface: str):
    try:
        subprocess.run(["sudo", "ip", "link", "set", iface, "down"], check=True)
        subprocess.run(["sudo", "iw", iface, "set", "type", "managed"], check=True)
        subprocess.run(["sudo", "ip", "link", "set", iface, "up"], check=True)
        logger.info(f"Successfully disabled monitor mode on {iface}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to disable monitor mode on {iface}: {str(e)}")
        return False
