#!/usr/bin/env bash
# run_all_servers.sh — start all three servers in the background, then tail logs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

PYTHON="${PYTHON:-python3}"

stop_all() {
    echo ""
    echo "Stopping servers..."
    kill "$PID_BANGLE" "$PID_PROCESSING" "$PID_UI" 2>/dev/null || true
    wait "$PID_BANGLE" "$PID_PROCESSING" "$PID_UI" 2>/dev/null || true
    echo "All servers stopped."
}

trap stop_all INT TERM

cd "$SCRIPT_DIR"

echo "Starting bangle_server.py (port 5007)..."
"$PYTHON" bangle_server.py >"$LOG_DIR/bangle_server.log" 2>&1 &
PID_BANGLE=$!

echo "Starting processing_server.py (port 5002)..."
"$PYTHON" processing_server.py >"$LOG_DIR/processing_server.log" 2>&1 &
PID_PROCESSING=$!

echo "Starting ui_server.py (port 5001)..."
"$PYTHON" ui_server.py >"$LOG_DIR/ui_server.log" 2>&1 &
PID_UI=$!

echo ""
echo "  nginx (entry point) : http://localhost:5000"
echo "  UI server           : http://localhost:5001  (pid $PID_UI)"
echo "  Processing server   : http://localhost:5002  (pid $PID_PROCESSING)"
echo "  Bangle server       : http://localhost:5007  (pid $PID_BANGLE)"
echo ""
echo "Use http://localhost:5000 — nginx routes to the right backend automatically."
echo "Logs in $LOG_DIR — press Ctrl+C to stop all."
echo ""

tail -f \
    "$LOG_DIR/bangle_server.log" \
    "$LOG_DIR/processing_server.log" \
    "$LOG_DIR/ui_server.log" &
PID_TAIL=$!

wait "$PID_BANGLE" "$PID_PROCESSING" "$PID_UI"
kill "$PID_TAIL" 2>/dev/null || true
