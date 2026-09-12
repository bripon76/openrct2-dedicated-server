# OpenRCT2 Server – OpenRCT2 Admin V16

Fix für Upload-Fehler wie `JSON.parse: line 1 column 1`.

- Antworten werden nicht mehr blind als JSON geparst.
- HTML/Text-Fehler werden jetzt lesbar angezeigt.
- API-Fehler werden serverseitig als JSON zurückgegeben.
- 413 (Upload zu groß), 404 und interne API-Ausnahmen liefern strukturierte Fehlermeldungen.

Neu bauen:

```bash
docker compose -f docker-compose.live-mac.yml down --remove-orphans
docker compose -f docker-compose.live-mac.yml build --no-cache admin
docker compose -f docker-compose.live-mac.yml up -d admin
docker compose -f docker-compose.live-mac.yml --profile game create openrct2
```
