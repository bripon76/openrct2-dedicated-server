# OpenRCT2 Server OpenRCT2 Serververwaltung

Webverwaltung fuer einen dedizierten OpenRCT2-Multiplayerserver.

## Architektur

| Dienst | Aufgabe | Port |
| --- | --- | --- |
| `admin` | Flask-Webinterface, API und Docker-Steuerung | `8088/tcp` |
| `openrct2` | OpenRCT2 CLI Gameserver | `11753/tcp` |

Die Admin-Bridge bleibt im Gameserver-Container auf `127.0.0.1:11754`. Der Admincontainer erreicht sie sicher ueber den Docker-Socket. Port `11754` wird nie veroeffentlicht.

## Funktionen

- Start, Stopp und Neustart des Gameservers aus dem Adminbereich.
- Zentraler Preflight fuer RCT2-Originaldaten und aktiven Spielstand.
- Upload und Auswahl von `.SV6`- und `.park`-Spielstaenden.
- Verwaltung von OpenRCT2-Spielergruppen und Gruppenrechten.
- Servername, Beschreibung, Begruessung, Spielerlimit und Webseitentitel.
- Oeffentliche Statusseite ohne Save-Download.
- Admin-Passwort kann im Adminbereich geaendert werden.
- Taegliche Backups des neuesten Autosaves mit sieben Tagen Aufbewahrung.
- Vier zufaellige Parkausschnitte alle fuenf Minuten, inklusive begrenztem Screenshot-Verlauf.

## Laufzeitdaten

`data/` ist absichtlich nicht Teil von Git. Es enthaelt originale RCT2-Dateien, Spielstaende, Backups, Screenshots und lokale Zugangsdaten.

```text
data/
├── config/
│   ├── config.ini
│   ├── save/
│   ├── backup/
│   └── screenshot/
└── rct2/
    ├── Data/
    └── ObjData/
```

## Lokale Entwicklung

```sh
docker compose -f docker-compose.live-mac.yml --profile game down --remove-orphans
docker compose -f docker-compose.live-mac.yml build --no-cache admin
docker compose -f docker-compose.live-mac.yml up -d admin
docker compose -f docker-compose.live-mac.yml --profile game create openrct2
```

Danach ist das Webinterface unter `http://localhost:8088/admin` erreichbar. Der Gameserver wird im Adminbereich gestartet.

## Alpine LXC

Der LXC benoetigt Docker-Nesting und mindestens zwei vCPU sowie zwei GB RAM. Die aktuelle Installation verwendet:

```text
LXC-IP: 192.168.1.231
Projekt: /opt/openrct2-admin
```

Die Datei `/opt/openrct2-admin/.env` wird nicht versioniert und muss mindestens enthalten:

```dotenv
ADMIN_PASSWORD=<sicheres-passwort>
SESSION_SECRET=<langer-zufaelliger-secret>
PUBLIC_HOST=openrct2.example.com
```

Nginx Proxy Manager leitet `openrct2.example.com` per HTTP an `<LXC-IP>:8088` weiter. Der Gameserver benoetigt eine direkte TCP-Weiterleitung von `11753` an den LXC; Nginx Proxy Manager ist kein OpenRCT2-TCP-Proxy.

## Erstes Git-Setup im vorhandenen LXC

Nach dem ersten Push nach GitHub einmal im LXC ausfuehren:

```sh
cd /opt/openrct2-admin
git init -b master
git remote add origin https://github.com/repository-owner/openrct2-dedicated-server.git
git fetch origin
git reset --hard origin/master
```

`data/` und `.env` bleiben dabei erhalten, weil sie von Git ignoriert werden.

## LXC aus Git aktualisieren

Nach jedem neuen GitHub-Push im LXC ausfuehren:

```sh
cd /opt/openrct2-admin
git pull --ff-only origin master
docker compose -f docker-compose.live-mac.yml build admin
docker compose -f docker-compose.live-mac.yml up -d admin
docker compose -f docker-compose.live-mac.yml --profile game up --no-start --force-recreate openrct2
```

Anschliessend den Gameserver im Adminbereich starten. Vor einem Update sollte ein Tagesbackup vorhanden sein.

## Pruefungen

```sh
python3 -m py_compile admin/app.py
docker compose -f docker-compose.live-mac.yml config
docker logs openrct2-admin
docker logs openrct2-server
```
