#!/bin/sh
set -eu

PROJECT_DIR="${1:-/opt/openrct2-admin}"

if [ ! -f "${PROJECT_DIR}/docker-compose.live-mac.yml" ]; then
    echo "Project files are missing in ${PROJECT_DIR}."
    echo "Copy this project to that directory before running this script."
    exit 1
fi

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "Create ${PROJECT_DIR}/.env first with ADMIN_PASSWORD and SESSION_SECRET."
    exit 1
fi

apk update
apk add docker docker-cli-compose bash
rc-update add docker default
service docker start

mkdir -p "${PROJECT_DIR}/data/config/save"
mkdir -p "${PROJECT_DIR}/data/config/screenshot"
mkdir -p "${PROJECT_DIR}/data/rct2"

cd "${PROJECT_DIR}"
docker compose -f docker-compose.live-mac.yml build admin
docker compose -f docker-compose.live-mac.yml up -d admin
docker compose -f docker-compose.live-mac.yml --profile game create openrct2

echo "Installation complete."
echo "NPM web target: http://<LXC-IP>:8088"
echo "Admin:          https://openrct2.example.com/admin"
echo "Public:         https://openrct2.example.com/public"
echo "Game:           openrct2.example.com:11753 (direct TCP)"
