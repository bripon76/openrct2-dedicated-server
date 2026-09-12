#!/usr/bin/env bash
set -euo pipefail
SAVE_DIR="data/config/save"
mkdir -p "$SAVE_DIR"
mapfile -t saves < <(find "$SAVE_DIR" -maxdepth 1 -type f \( -iname '*.sv6' -o -iname '*.park' \) -printf '%f\n' | sort)
if [ "${#saves[@]}" -eq 1 ]; then
  printf '%s\n' "${saves[0]}" > "$SAVE_DIR/.active-save"
  echo "Aktiver Spielstand: ${saves[0]}"
elif [ "${#saves[@]}" -eq 0 ]; then
  echo "Kein Save gefunden."
  exit 1
else
  echo "Mehrere Saves gefunden. Bitte im WebIF einen auswählen:"
  printf ' - %s\n' "${saves[@]}"
  exit 2
fi
