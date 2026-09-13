#!/bin/sh
set -eu

PROJECT_DIR="${1:-/opt/openrct2-admin}"
REPOSITORY="${2:-${REPOSITORY:-}}"
BRANCH="${BRANCH:-master}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root inside the Alpine LXC."
    exit 1
fi
if [ -z "${REPOSITORY}" ]; then
    echo "Usage: ADMIN_PASSWORD='...' $0 [project-dir] <git-repository-url>"
    exit 1
fi
if [ -z "${ADMIN_PASSWORD:-}" ]; then
    echo "Set ADMIN_PASSWORD to a strong password before installation."
    exit 1
fi

apk update
apk add docker docker-cli-compose bash git openssl
rc-update add docker default
service docker start

if [ -e "${PROJECT_DIR}" ] && [ ! -d "${PROJECT_DIR}/.git" ]; then
    echo "${PROJECT_DIR} exists but is not a Git checkout. Move it aside before installing."
    exit 1
fi
if [ ! -d "${PROJECT_DIR}/.git" ]; then
    git clone --branch "${BRANCH}" --single-branch "${REPOSITORY}" "${PROJECT_DIR}"
fi

umask 077
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    SESSION_SECRET="$(openssl rand -hex 32)"
    printf '%s\n' \
        "ADMIN_PASSWORD=${ADMIN_PASSWORD}" \
        "SESSION_SECRET=${SESSION_SECRET}" \
        "PUBLIC_HOST=${PUBLIC_HOST:-openrct2.example.com}" > "${PROJECT_DIR}/.env"
fi

mkdir -p "${PROJECT_DIR}/data/config/save" "${PROJECT_DIR}/data/config/screenshot" "${PROJECT_DIR}/data/rct2"
chown -R 1001:1001 "${PROJECT_DIR}/data/config"

cd "${PROJECT_DIR}"
docker compose build admin
docker compose up -d admin
docker compose --profile game create openrct2
docker compose ps

echo "Installation complete."
echo "Web proxy target: http://<LXC-IP>:8088"
echo "Open /admin and complete the first-start wizard."
echo "Forward TCP port 11753 directly to this LXC for OpenRCT2 clients."
