#!/bin/bash

# Script to kill all hostapd-mana processes
# Usage: ./kill_hostapd_mana.sh

echo "Stopping all hostapd-mana processes..."

# Try to kill all hostapd-mana processes
if sudo killall hostapd-mana 2>/dev/null; then
    echo "Successfully killed all hostapd-mana processes"
    exit 0
else
    # If no processes found, it's still a success
    echo "No hostapd-mana processes found"
    exit 0
fi
