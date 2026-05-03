#!/usr/bin/env bash
# dev.sh — Run in Docker with DEBUG=true (local only)
set -e
cd "$(dirname "$0")"

echo "[dev] Setting DEBUG=true..."
sed -i 's/^DEBUG=.*/DEBUG=true/' .env

echo "[dev] Starting Docker containers..."
sudo docker compose up --build

