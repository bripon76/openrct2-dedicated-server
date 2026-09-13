#!/usr/bin/env bash
set -euo pipefail

SAVE_DIR="${SAVE_DIR:-/home/openrct2/.config/OpenRCT2/save}"
ACTIVE_FILE="${ACTIVE_SAVE_FILE:-${SAVE_DIR}/.active-save}"
RCT2_DATA="${RCT2_DATA_DIR:-/rct2}"
PORT="${OPENRCT2_PORT:-11753}"

mkdir -p "/home/openrct2/.config/OpenRCT2/screenshot"

echo "[openrct2-admin] OpenRCT2 live launcher"
echo "[openrct2-admin] validating original RCT2 data..."

if [[ ! -f "${RCT2_DATA}/Data/g1.dat" ]]; then
  echo "[openrct2-admin] ERROR: ${RCT2_DATA}/Data/g1.dat missing"
  exit 20
fi
if [[ ! -d "${RCT2_DATA}/ObjData" ]]; then
  echo "[openrct2-admin] ERROR: ${RCT2_DATA}/ObjData missing"
  exit 21
fi
if [[ ! -s "${ACTIVE_FILE}" ]]; then
  echo "[openrct2-admin] no active save marker found; scanning save directory..."
  mapfile -t SAVE_CANDIDATES < <(find "${SAVE_DIR}" -maxdepth 1 -type f \( -iname '*.sv6' -o -iname '*.park' \) -printf '%f\n' | sort)

  if [[ ${#SAVE_CANDIDATES[@]} -eq 0 ]]; then
    echo "[openrct2-admin] ERROR: no .SV6 or .park save found"
    exit 22
  elif [[ ${#SAVE_CANDIDATES[@]} -eq 1 ]]; then
    SAVE_NAME="${SAVE_CANDIDATES[0]}"
    printf '%s\n' "${SAVE_NAME}" > "${ACTIVE_FILE}"
    echo "[openrct2-admin] automatically selected only save: ${SAVE_NAME}"
  else
    echo "[openrct2-admin] ERROR: multiple saves found but none selected:"
    printf '  - %s\n' "${SAVE_CANDIDATES[@]}"
    exit 22
  fi
else
  SAVE_NAME="$(tr -d '\r\n' < "${ACTIVE_FILE}")"
fi
case "${SAVE_NAME,,}" in
  *.sv6|*.park) ;;
  *) echo "[openrct2-admin] ERROR: invalid active save extension"; exit 23 ;;
esac

SAVE_PATH="${SAVE_DIR}/${SAVE_NAME}"
if [[ ! -f "${SAVE_PATH}" ]]; then
  echo "[openrct2-admin] ERROR: active save not found: ${SAVE_PATH}"
  exit 24
fi

# Continue from a newer autosave unless the user selected another save later.
LATEST_AUTOSAVE=""
if [[ -d "${SAVE_DIR}/autosave" ]]; then
  LATEST_AUTOSAVE="$(find "${SAVE_DIR}/autosave" -maxdepth 1 -type f \( -iname '*.sv6' -o -iname '*.park' \) -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2- | head -n 1)"
fi
if [[ -n "${LATEST_AUTOSAVE}" && "${LATEST_AUTOSAVE}" -nt "${ACTIVE_FILE}" ]]; then
  SAVE_PATH="${LATEST_AUTOSAVE}"
  echo "[openrct2-admin] continuing from autosave: $(basename "${SAVE_PATH}")"
fi

echo "[openrct2-admin] starting: ${SAVE_NAME} on TCP ${PORT}"
exec openrct2-cli host "${SAVE_PATH}"   --headless   --port "${PORT}"   --user-data-path /home/openrct2/.config/OpenRCT2   --rct2-data-path "${RCT2_DATA}"
