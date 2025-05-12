#!/bin/bash

# Port yang digunakan
PORT=8000

# Cari proses yang menggunakan port tersebut
PID=$(lsof -ti tcp:$PORT)

if [ -n "$PID" ]; then
    echo "Stopping process on port $PORT (PID: $PID)"
    kill -9 $PID
    echo "Stopped."
else
    echo "No process found running on port $PORT."
fi
