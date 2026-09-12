#!/usr/bin/env bash
set -euo pipefail

SAVE_DIR="${SAVE_DIR:-/home/openrct2/.config/OpenRCT2/save}"
ACTIVE_FILE="${ACTIVE_SAVE_FILE:-${SAVE_DIR}/.active-save}"
RCT2_DATA="${RCT2_DATA_DIR:-/rct2}"
PORT="${OPENRCT2_PORT:-11753}"

mkdir -p "/home/openrct2/.config/OpenRCT2/screenshot"

echo "[serververwalter] OpenRCT2 live launcher"
echo "[serververwalter] validating original RCT2 data..."

if [[ ! -f "${RCT2_DATA}/Data/g1.dat" ]]; then
  echo "[serververwalter] ERROR: ${RCT2_DATA}/Data/g1.dat missing"
  exit 20
fi
if [[ ! -d "${RCT2_DATA}/ObjData" ]]; then
  echo "[serververwalter] ERROR: ${RCT2_DATA}/ObjData missing"
  exit 21
fi
if [[ ! -s "${ACTIVE_FILE}" ]]; then
  echo "[serververwalter] no active save marker found; scanning save directory..."
  mapfile -t SAVE_CANDIDATES < <(find "${SAVE_DIR}" -maxdepth 1 -type f \( -iname '*.sv6' -o -iname '*.park' \) -printf '%f\n' | sort)

  if [[ ${#SAVE_CANDIDATES[@]} -eq 0 ]]; then
    echo "[serververwalter] ERROR: no .SV6 or .park save found"
    exit 22
  elif [[ ${#SAVE_CANDIDATES[@]} -eq 1 ]]; then
    SAVE_NAME="${SAVE_CANDIDATES[0]}"
    printf '%s\n' "${SAVE_NAME}" > "${ACTIVE_FILE}"
    echo "[serververwalter] automatically selected only save: ${SAVE_NAME}"
  else
    echo "[serververwalter] ERROR: multiple saves found but none selected:"
    printf '  - %s\n' "${SAVE_CANDIDATES[@]}"
    exit 22
  fi
else
  SAVE_NAME="$(tr -d '\r\n' < "${ACTIVE_FILE}")"
fi
case "${SAVE_NAME,,}" in
  *.sv6|*.park) ;;
  *) echo "[serververwalter] ERROR: invalid active save extension"; exit 23 ;;
esac

SAVE_PATH="${SAVE_DIR}/${SAVE_NAME}"
if [[ ! -f "${SAVE_PATH}" ]]; then
  echo "[serververwalter] ERROR: active save not found: ${SAVE_PATH}"
  exit 24
fi

echo "[serververwalter] starting: ${SAVE_NAME} on TCP ${PORT}"
exec openrct2-cli host "${SAVE_PATH}"   --headless   --port "${PORT}"   --user-data-path /home/openrct2/.config/OpenRCT2   --rct2-data-path "${RCT2_DATA}"
