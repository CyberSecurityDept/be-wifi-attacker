import subprocess


def enable_monitor(iface: str):
    subprocess.run(["ip", "link", "set", iface, "down"], check=True)
    subprocess.run(["iw", iface, "set", "monitor", "none"], check=True)
    subprocess.run(["ip", "link", "set", iface, "up"], check=True)


def disable_monitor(iface: str):
    subprocess.run(["ip", "link", "set", iface, "down"], check=True)
    subprocess.run(["iw", iface, "set", "type", "managed"], check=True)
    subprocess.run(["ip", "link", "set", iface, "up"], check=True)
