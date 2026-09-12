#!/usr/bin/env bash
set -e
docker compose -f docker-compose.live-mac.yml up --build -d admin
docker compose -f docker-compose.live-mac.yml --profile game create openrct2
echo
echo "Admin/Public läuft dauerhaft:"
echo "  http://localhost:8088/"
echo "  http://localhost:8088/admin"
echo
echo "Der OpenRCT2-Container wurde nur vorbereitet, NICHT gestartet."
echo "Originaldaten und Savegame jetzt über den Wizard hochladen."
