#!/usr/bin/env bash
# dev.sh — Run in Docker with DEBUG=true, exposed via ngrok
set -e
cd "$(dirname "$0")"

echo "[dev] Setting DEBUG=true..."
sed -i 's/^DEBUG=.*/DEBUG=true/' .env

echo "[dev] Starting Docker containers (detached)..."
sudo docker compose up -d --build

echo "[dev] Containers up. Starting ngrok on port 5000..."
echo "  (Ctrl+C to stop ngrok — containers keep running)"
echo ""
ngrok http 5000 --url https://noonchi.ngrok.io

