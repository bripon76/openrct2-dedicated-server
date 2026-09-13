#!/bin/sh
set -eu

PROJECT_DIR="${1:-/opt/openrct2-admin}"
BRANCH="${BRANCH:-master}"

if [ ! -d "${PROJECT_DIR}/.git" ]; then
    echo "${PROJECT_DIR} is not a Git checkout. Run install-alpine-lxc.sh first."
    exit 1
fi
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "${PROJECT_DIR}/.env is missing. Refusing to start with insecure defaults."
    exit 1
fi

cd "${PROJECT_DIR}"
if [ -f data/config/.openrct2-image ]; then
    OPENRCT2_IMAGE=$(tr -d '\r\n' < data/config/.openrct2-image)
    if printf '%s\n' "${OPENRCT2_IMAGE}" | grep -Eq '^openrct2/openrct2-cli:[0-9]+\.[0-9]+\.[0-9]+$'; then
        export OPENRCT2_IMAGE
    else
        echo "Ignoring invalid persisted OpenRCT2 image."
        unset OPENRCT2_IMAGE
    fi
fi
was_running=false
if docker inspect -f '{{.State.Running}}' openrct2-server 2>/dev/null | grep -qx true; then
    was_running=true
fi

git fetch origin "${BRANCH}"
git checkout -B "${BRANCH}" "origin/${BRANCH}"
git reset --hard "origin/${BRANCH}"

mkdir -p data/config/save data/config/screenshot data/rct2
chown -R 1001:1001 data/config

docker compose build admin
docker compose up -d admin
docker compose --profile game rm -sf openrct2 >/dev/null 2>&1 || true
if [ "${was_running}" = true ]; then
    docker compose --profile game up -d openrct2
else
    docker compose --profile game create openrct2
fi
docker compose ps
