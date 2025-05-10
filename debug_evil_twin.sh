#!/bin/bash
# debug_evil_twin.sh
# Usage: sudo ./debug_evil_twin.sh <internet_interface> <ap_interface> <hotspot_name>

set -e

INTERNET_IFACE="$1"
AP_IFACE="$2"
HOTSPOT_NAME="$3"

if [[ -z "$INTERNET_IFACE" || -z "$AP_IFACE" || -z "$HOTSPOT_NAME" ]]; then
  echo "Usage: sudo $0 <internet_interface> <ap_interface> <hotspot_name>"
  exit 1
fi

echo "[DEBUG] Starting create_ap..."
sudo create_ap "$INTERNET_IFACE" "$AP_IFACE" "$HOTSPOT_NAME" &
CREATE_AP_PID=$!
sleep 2

echo "[DEBUG] Setting up iptables rules..."
sudo iptables -A FORWARD -i ap0 -o "$INTERNET_IFACE" -j ACCEPT
sudo iptables -A FORWARD -i "$INTERNET_IFACE" -o ap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o "$INTERNET_IFACE" -j MASQUERADE

echo "[DEBUG] Enabling IP forwarding..."
sudo sysctl -w net.ipv4.ip_forward=1

echo "[DEBUG] Evil twin hotspot '$HOTSPOT_NAME' started."
echo "[DEBUG] create_ap PID: $CREATE_AP_PID"
echo "Tekan [ENTER] untuk menghentikan create_ap dan membersihkan iptables..."
read

echo "[DEBUG] Stopping create_ap..."
sudo kill "$CREATE_AP_PID"
wait "$CREATE_AP_PID" 2>/dev/null

echo "[DEBUG] Flushing iptables rules..."
sudo iptables -D FORWARD -i ap0 -o "$INTERNET_IFACE" -j ACCEPT
sudo iptables -D FORWARD -i "$INTERNET_IFACE" -o ap0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -t nat -D POSTROUTING -o "$INTERNET_IFACE" -j MASQUERADE

echo "[DEBUG] Evil twin hotspot stopped and iptables cleaned."
