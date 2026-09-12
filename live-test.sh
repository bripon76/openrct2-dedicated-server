#!/usr/bin/env bash
set -e
echo "=== OpenRCT2 Server OpenRCT2 V9 ==="
docker compose -f docker-compose.live-mac.yml down --remove-orphans 2>/dev/null || true
docker compose -f docker-compose.live-mac.yml up --build -d admin
echo
echo "Public: http://localhost:8088/"
echo "Admin:  http://localhost:8088/admin"
echo
echo "Open the admin setup wizard. The game server stays stopped until setup is complete."
