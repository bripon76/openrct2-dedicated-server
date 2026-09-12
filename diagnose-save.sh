#!/usr/bin/env bash
set -e
echo "=== save directory ==="
ls -la data/config/save || true
echo
echo "=== active marker ==="
if [ -f data/config/save/.active-save ]; then
  cat data/config/save/.active-save
else
  echo "(missing)"
fi
echo
echo "=== detected saves ==="
find data/config/save -maxdepth 1 -type f \( -iname "*.sv6" -o -iname "*.park" \) -print
