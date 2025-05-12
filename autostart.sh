#!/bin/bash

# Nama file log
LOG_FILE="app.log"

# Port yang digunakan
PORT=8000

# Direktori kerja (pastikan ini sesuai)
PROJECT_DIR="/home/rnd/Developments/be-wifi-attacker"

# Aktifkan virtualenv (pastikan path ini sesuai)
source "$PROJECT_DIR/venv/bin/activate"

# Cari dan kill proses yang pakai port 8000
PID=$(lsof -ti tcp:$PORT)
if [ -n "$PID" ]; then
    echo "Killing process on port $PORT (PID: $PID)"
    kill -9 $PID
fi

# Pindah ke direktori proyek
cd "$PROJECT_DIR"

# Jalankan uvicorn dan log ke file
echo "Starting uvicorn on 0.0.0.0:$PORT..."
nohup uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload > "$LOG_FILE" 2>&1 &

echo "Server started and logging to $LOG_FILE"
