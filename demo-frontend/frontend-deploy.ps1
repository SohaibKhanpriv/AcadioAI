Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# === Config ===
$SERVER_IP = "161.35.139.40"
$SSH_USER = "acadlo"
$SSH_KEY_PATH = "C:/acadlo-key"
$REMOTE_DIR = "/home/acadlo/acadlo-frontend"

$IMAGE_NAME = "acadlo-ai-frontend"
$IMAGE_TAG = "latest"
$TAR_NAME = "acadlo-ai-frontend.tar"

$ENV_FILE = ".env.frontend"
$COMPOSE_FILE = "docker-compose.frontend.yml"

# === Build image ===
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

# === Save image ===
docker save "${IMAGE_NAME}:${IMAGE_TAG}" -o "${TAR_NAME}"

# === Ensure remote directory exists and is writable ===
ssh -v -i "${SSH_KEY_PATH}" "${SSH_USER}@${SERVER_IP}" "mkdir -p '${REMOTE_DIR}'"

# === Upload artifacts ===
scp -v -i "${SSH_KEY_PATH}" "${TAR_NAME}" "${SSH_USER}@${SERVER_IP}:${REMOTE_DIR}/"
scp -v -i "${SSH_KEY_PATH}" "${ENV_FILE}" "${SSH_USER}@${SERVER_IP}:${REMOTE_DIR}/"
scp -v -i "${SSH_KEY_PATH}" "${COMPOSE_FILE}" "${SSH_USER}@${SERVER_IP}:${REMOTE_DIR}/"

# === Deploy on server ===
ssh -v -i "${SSH_KEY_PATH}" "${SSH_USER}@${SERVER_IP}" @"
set -e
cd "${REMOTE_DIR}"

docker compose -f "${COMPOSE_FILE}" down || true
docker rmi -f "${IMAGE_NAME}:${IMAGE_TAG}" || true
docker load -i "${TAR_NAME}"
docker compose -f "${COMPOSE_FILE}" up -d
"@

Write-Host "✅ Frontend deployed successfully."
