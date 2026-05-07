#!/usr/bin/env bash
# dev.sh — Run in Docker with DEBUG=true, exposed via ngrok
set -e
cd "$(dirname "$0")"

free_port_5000() {
	echo "[dev] Checking port 5000..."

	# Prefer stopping Docker containers that already publish port 5000.
	local bound_containers
	bound_containers=$(sudo docker ps --format '{{.ID}} {{.Ports}}' | awk '/0\.0\.0\.0:5000->|:::5000->/ {print $1}')
	if [[ -n "$bound_containers" ]]; then
		echo "[dev] Stopping container(s) using port 5000: $bound_containers"
		sudo docker stop $bound_containers >/dev/null || true
	fi

	# If port is still in use by a host process, kill the listener.
	if sudo ss -ltn | awk 'NR>1 {print $4}' | grep -qE '(^|:)5000$'; then
		echo "[dev] Port 5000 is still busy. Killing listener(s)..."
		if command -v fuser >/dev/null 2>&1; then
			sudo fuser -k 5000/tcp >/dev/null 2>&1 || true
		else
			local pids
			pids=$(sudo lsof -t -iTCP:5000 -sTCP:LISTEN 2>/dev/null || true)
			if [[ -n "$pids" ]]; then
				sudo kill -9 $pids >/dev/null 2>&1 || true
			fi
		fi
	fi
}

echo "[dev] Setting DEBUG=true..."
sed -i 's/^DEBUG=.*/DEBUG=true/' .env

free_port_5000

echo "[dev] Starting Docker containers (detached)..."
sudo docker compose up -d --build
sudo docker compose restart nginx

echo "[dev] Containers up. Starting ngrok on port 5000..."
echo "  (Ctrl+C to stop ngrok — containers keep running)"
echo ""
ngrok http 5000 --url https://noonchi.ngrok.io

