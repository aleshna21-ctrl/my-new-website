#!/usr/bin/env bash
# ==============================================================================
# AIOS Command Center — Hostinger VPS SSH Deployment Script
# Target: root@2.25.249.27 | Port: 5050 (http://2.25.249.27:5050/)
# ==============================================================================
set -euo pipefail

VPS_USER="${VPS_USER:-root}"
VPS_IP="${VPS_IP:-2.25.249.27}"
VPS_HOST="${VPS_USER}@${VPS_IP}"
REMOTE_DIR="${REMOTE_DIR:-/opt/aios}"
PORT="${PORT:-5050}"
BIND_IP="${BIND_IP:-0.0.0.0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Package project files locally
BUNDLE="/tmp/aios-deploy-$$.tar.gz"
trap 'rm -f "$BUNDLE"' EXIT

echo "[1/3] Packaging AIOS project files..."

# Dynamically aggregate paths that exist locally to prevent tar stat aborts
CANDIDATE_ITEMS=(
"Dockerfile" "compose.yml" ".dockerignore" ".env" ".env.example" "requirements.txt"
"vps-backup-and-auth.sh" "hud_server.py" "app.py" "index.html" "package.json"
"inference_adapter.py" "data_contracts.py" "hermes_8080_server.py" "offline_observer.py" "offline_telemetry.py"
"job_ledger.py" "smtp_alert_relay.py" "hud" "static" "config" "data" "inbox" "plugins"
)
FILES_TO_PACK=()
for item in "${CANDIDATE_ITEMS[@]}"; do
if [ -e "$item" ]; then
FILES_TO_PACK+=("$item")
fi
done

if [ ${#FILES_TO_PACK[@]} -eq 0 ]; then
echo "ERROR: No deployable project files found in ${SCRIPT_DIR}." >&2
exit 1
fi

tar -czf "$BUNDLE" \
--exclude=".git" \
--exclude="__pycache__" \
--exclude="*.pyc" \
--exclude=".pytest_cache" \
--exclude="tests" \
--exclude="docs" \
--exclude="state/server" \
--exclude="*.tmp*" \
"${FILES_TO_PACK[@]}"

# 2. Transfer archive and execute remote orchestration across isolated SSH channels
echo "[2/3] Connecting to ${VPS_HOST} via SSH to sync and launch on port ${PORT}..."

# Stage 2A: Stream and unpack archive directly into target directory
ssh -o StrictHostKeyChecking=accept-new "$VPS_HOST" \
"mkdir -p '${REMOTE_DIR}' && tar -xzf - -C '${REMOTE_DIR}'" < "$BUNDLE"

# Stage 2B: Execute host configuration, Docker Compose build, and verification
ssh -o StrictHostKeyChecking=accept-new "$VPS_HOST" \
"REMOTE_DIR='$REMOTE_DIR' PORT='$PORT' BIND_IP='$BIND_IP' VPS_IP='$VPS_IP' bash -s" <<'REMOTE_EOF'
set -euo pipefail

echo "---> [VPS] Preparing ${REMOTE_DIR} persistent directory structure..."
mkdir -p "${REMOTE_DIR}/data" \
"${REMOTE_DIR}/scratch" \
"${REMOTE_DIR}/vault" \
"${REMOTE_DIR}/calendar" \
"${REMOTE_DIR}/backups"

cd "${REMOTE_DIR}"

if [ -f vps-backup-and-auth.sh ]; then
sed -i 's/\r$//' vps-backup-and-auth.sh 2>/dev/null || true
chmod +x vps-backup-and-auth.sh
fi

echo "---> [VPS] Configuring .env for port ${PORT} (${BIND_IP})..."
if [ ! -f .env ]; then
if [ -f .env.example ]; then
cp .env.example .env
else
touch .env
fi
fi

# Ensure baseline keys exist before replacement
grep -q "^HUD_BIND_IP=" .env || echo "HUD_BIND_IP=${BIND_IP}" >> .env
grep -q "^HUD_PORT=" .env || echo "HUD_PORT=${PORT}" >> .env

sed -i "s/^HUD_BIND_IP=.*/HUD_BIND_IP=${BIND_IP}/" .env
sed -i "s/^HUD_PORT=.*/HUD_PORT=${PORT}/" .env

# Verify Docker and Docker Compose plugin availability
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
echo "---> [VPS] Installing Docker Engine & Docker Compose plugin..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin
systemctl enable --now docker
fi

# Configure guest firewall if UFW is active
if command -v ufw >/dev/null 2>&1; then
if ufw status | grep -q "Status: active"; then
echo "---> [VPS] Allowing TCP port ${PORT} in UFW firewall..."
ufw allow "${PORT}/tcp" >/dev/null || true
fi
fi

echo "---> [VPS] Building and starting Docker Compose stack on port ${PORT}..."
docker compose up -d --build --force-recreate --remove-orphans

echo "---> [VPS] Awaiting AIOS service responsiveness..."
MAX_RETRIES=15
RETRY_COUNT=0
HEALTHY=0

until [ $RETRY_COUNT -ge $MAX_RETRIES ]; do
if command -v curl >/dev/null 2>&1; then
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/api/os/telemetry" || true)
if [ "$HTTP_CODE" = "200" ]; then
HEALTHY=1
break
fi
elif command -v python3 >/dev/null 2>&1; then
if python3 -c "import urllib.request; exit(0 if urllib.request.urlopen('http://127.0.0.1:${PORT}/api/os/telemetry', timeout=2).getcode()==200 else 1)" 2>/dev/null; then
HEALTHY=1
break
fi
fi
RETRY_COUNT=$((RETRY_COUNT + 1))
sleep 2
done

docker compose ps

if [ $HEALTHY -eq 1 ]; then
echo "---> [VPS] Verifying live telemetry response on port ${PORT}..."
if command -v curl >/dev/null 2>&1; then
TELEMETRY=$(curl -s "http://127.0.0.1:${PORT}/api/os/telemetry")
echo "LIVE TELEMETRY VERIFIED -> HTTP 200 | Payload: ${TELEMETRY}"
elif command -v python3 >/dev/null 2>&1; then
python3 -c "import urllib.request, json; r=urllib.request.urlopen('http://127.0.0.1:${PORT}/api/os/telemetry', timeout=5); d=json.loads(r.read()); print('LIVE TELEMETRY VERIFIED -> HTTP', r.status, '| ts:', d.get('ts'), '| hash:', d.get('hash'))"
fi
else
echo "WARNING: Telemetry endpoint health check timed out after $((MAX_RETRIES * 2)) seconds." >&2
echo "Review container status and application logs using: docker compose logs" >&2
exit 1
fi
REMOTE_EOF

echo ""
echo "[3/3] Deployment complete!"
echo " Open your AIOS Command Center at: http://${VPS_IP}:${PORT}/"