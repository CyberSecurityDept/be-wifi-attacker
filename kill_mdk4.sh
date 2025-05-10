#!/bin/bash

# Script to kill mdk4 processes
# Usage: sudo ./kill_mdk4.sh [BSSID]

if [ $# -eq 0 ]; then
  # Kill all mdk4 processes if no BSSID is provided
  pkill -9 -f 'mdk4'
  echo "Killed all mdk4 processes"
else
  # Kill specific mdk4 processes for the given BSSID
  BSSID=$1
  pkill -9 -f "mdk4.*-B $BSSID"
  echo "Killed mdk4 processes for BSSID: $BSSID"
fi

exit 0
