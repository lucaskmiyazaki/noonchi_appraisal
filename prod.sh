#!/usr/bin/env bash
# prod.sh — Run in Docker with DEBUG=false, exposed via ngrok
set -e
cd "$(dirname "$0")"

echo "[prod] Setting DEBUG=false..."
sed -i 's/^DEBUG=.*/DEBUG=false/' .env

echo "[prod] Starting Docker containers (detached)..."
sudo docker compose up -d --build

echo "[prod] Containers up. Starting ngrok on port 5000..."
echo "  (Ctrl+C to stop ngrok — containers keep running)"
echo ""
ngrok http 5000

