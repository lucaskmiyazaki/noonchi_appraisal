#!/usr/bin/env bash
# prod.sh — Run in production on noonchi.live with HTTPS
set -e
cd "$(dirname "$0")"

DOMAIN="noonchi.live"
EMAIL="admin@noonchi.live"
CERT="./letsencrypt/live/${DOMAIN}/fullchain.pem"

echo "[prod] Setting DEBUG=false..."
sed -i 's/^DEBUG=.*/DEBUG=false/' .env

# ── Step 1: GCP firewall — open ports 80 and 443 ─────────────────────────────
echo "[prod] Checking GCP firewall rules..."
if command -v gcloud &>/dev/null; then
  # Check if the rule already exists
  if ! gcloud compute firewall-rules describe allow-noonchi-web &>/dev/null 2>&1; then
    echo "[prod] Creating firewall rule to allow ports 80 and 443..."
    if gcloud compute firewall-rules create allow-noonchi-web \
      --allow tcp:80,tcp:443 \
      --direction=INGRESS \
      --priority=1000 \
      --description="Allow HTTP and HTTPS for noonchi.live" 2>/dev/null; then
      echo "[prod] Firewall rule created."
    else
      echo ""
      echo "[prod] ⚠ Could not create firewall rule via gcloud (insufficient auth scopes)."
      echo "       Fix with one of these options:"
      echo ""
      echo "       Option A — re-authenticate gcloud and retry:"
      echo "         gcloud auth login"
      echo "         gcloud compute firewall-rules create allow-noonchi-web --allow tcp:80,tcp:443"
      echo ""
      echo "       Option B — create via GCP Console (no auth needed):"
      echo "         https://console.cloud.google.com/networking/firewalls/add"
      echo "         Name: allow-noonchi-web"
      echo "         Direction: Ingress | Action: Allow | Targets: All instances"
      echo "         Protocols/ports: tcp:80, tcp:443"
      echo ""
      echo "       Continuing — ports may already be open..."
    fi
  else
    echo "[prod] Firewall rule already exists — skipping."
  fi
else
  echo "[prod] gcloud not found — skipping firewall setup."
  echo "       If ports 80/443 are not open, run manually:"
  echo "       gcloud compute firewall-rules create allow-noonchi-web --allow tcp:80,tcp:443"
fi

# ── Step 2: Detect this VM's external IP ─────────────────────────────────────
VM_IP=$(curl -sf --max-time 3 "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/externalIp" -H "Metadata-Flavor: Google" || true)
if [ -z "$VM_IP" ]; then
  # Fallback: ask an external service
  VM_IP=$(curl -sf --max-time 5 https://api.ipify.org || echo "unknown")
fi
echo "[prod] VM external IP: ${VM_IP}"

# ── Step 3: Verify DNS resolves to this VM ───────────────────────────────────
echo "[prod] Checking DNS for ${DOMAIN}..."
DNS_IP=$(dig +short "${DOMAIN}" A | tail -1)
if [ -z "$DNS_IP" ]; then
  echo ""
  echo "[prod] ⚠ DNS not yet configured for ${DOMAIN}."
  echo "       In Squarespace Domains → noonchi.live → DNS Settings, add:"
  echo ""
  echo "       Type  Name   Value"
  echo "       A     @      ${VM_IP}"
  echo "       A     www    ${VM_IP}"
  echo ""
  echo "       DNS can take a few minutes to propagate."
  echo "       Re-run prod.sh once DNS is pointing to this VM."
  exit 1
elif [ "$DNS_IP" != "$VM_IP" ] && [ "$VM_IP" != "unknown" ]; then
  echo ""
  echo "[prod] ⚠ ${DOMAIN} resolves to ${DNS_IP}, but this VM is ${VM_IP}."
  echo "       Update your DNS A record to point to ${VM_IP}."
  echo "       Re-run prod.sh once DNS propagates."
  exit 1
else
  echo "[prod] DNS OK — ${DOMAIN} → ${DNS_IP}"
fi

# ── Step 4: Issue TLS certificate (first run only) ───────────────────────────
if [ ! -f "$CERT" ]; then
  echo "[prod] No TLS cert found — issuing certificate for ${DOMAIN}..."

  mkdir -p ./letsencrypt ./certbot-www

  # Start a temporary nginx on port 80 to serve the ACME challenge
  sudo docker run -d --name certbot-init-nginx \
    -p 80:80 \
    -v "$(pwd)/docker/nginx.init.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "$(pwd)/certbot-www:/var/www/certbot" \
    nginx:alpine

  # Issue the cert via webroot challenge
  sudo docker run --rm \
    -v "$(pwd)/letsencrypt:/etc/letsencrypt" \
    -v "$(pwd)/certbot-www:/var/www/certbot" \
    certbot/certbot certonly \
      --webroot --webroot-path=/var/www/certbot \
      --email "${EMAIL}" --agree-tos --non-interactive \
      -d "${DOMAIN}" -d "www.${DOMAIN}"

  # Stop temporary nginx
  sudo docker stop certbot-init-nginx && sudo docker rm certbot-init-nginx

  echo "[prod] Certificate issued successfully."
else
  echo "[prod] TLS cert found — skipping issuance."
fi

# ── Step 5: Start all containers ─────────────────────────────────────────────
echo "[prod] Building and starting containers..."
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ""
echo "[prod] ✓ Running at https://${DOMAIN}"

