# OpenRCT2 Server Admin

<p align="center"><img src="admin/static/openrct2-server-logo.png" alt="OpenRCT2 Server" width="260"></p>

Webverwaltung fuer einen dedizierten OpenRCT2-Multiplayerserver. Der Quellcode wird aus Git installiert; Spielinhalte und Zugangsdaten werden ausschliesslich ueber den Wizard oder den Adminbereich in die lokale Laufzeitumgebung eingebracht.

Eine statische Design-Vorschau liegt unter [`docs/demo.html`](docs/demo.html). Fuer GitHub Pages den Ordner `docs/` als Pages-Quelle aktivieren.

## Architektur

| Dienst | Aufgabe | Port |
| --- | --- | --- |
| `admin` | Flask-Admin, Public-Seite, API und Docker-Steuerung | `8088/tcp` |
| `openrct2` | OpenRCT2-Multiplayerserver | `11753/tcp` |

Die lokale Admin-Bridge verwendet `127.0.0.1:11754` innerhalb des Gameserver-Containers. Dieser Port wird nie veroeffentlicht.

## Funktionen

- Responsive Admin- und Public-Oberflaeche im OpenRCT2-Parkdesign.
- Ersteinrichtung fuer RCT2-Originaldaten, Savegame und Servereinstellungen.
- Save-Upload, Aktivierung, sicherer Loeschschutz des aktiven Saves, Tagesbackups und authentifizierter Backup-Download.
- Serverstart, Stopp, Neustart, Preflight, aufklappbare Containerlogs und Parkansichten.
- Separate Public-Freigaben fuer Serverdetails, Spieler, Parkansichten, Live-Parkdaten und Live-Ankuendigungen.
- Gruppen- und Rechteverwaltung mit sicherem Moderatorprofil ohne `passwordless_login` und `set_player_group`.
- Live-Parkdaten: Besucher, Finanzen, Kredit, Eintritt und Preise, Park- und Firmenwert, Rating, Eintritte, Besuchergenerierung, Parkgroesse, Forschung, Auszeichnungen und Parkflags.
- Live-Ankuendigungen aus OpenRCT2, etwa Ride-Breakdowns und Warnungen, sind im Admin sichtbar und bei aktivierter Freigabe auch auf der Public-Seite.
- Admin-Aktion mit expliziter Bestaetigung: Nachricht an alle verbundenen Spieler.
- Optionaler Public-Infobereich, konfigurierbare Footer, Serveradresse und Branding-Upload.
- DDNS-/OpenRCT2-Werbeadresse in `[network] advertise_address` mit sicherer Host-, IPv4- oder geklammerter-IPv6-Pruefung.
- Manuelle Auswahl stabiler OpenRCT2-Container-Versionen mit Backup und Rollback.

### OpenRCT2-Grenzen

OpenRCT2 `0.5.5` erlaubt Remote-Plugins das Lesen der genannten Parkdaten und das Senden einer Servernachricht. Direkte Aenderungen von Parkeigenschaften, Besuchergenerierung, Parkflags, Auszeichnungen und Parknachrichten werden von dieser Version mit `Game state is not mutable in this context` abgewiesen und werden daher nicht angeboten.

Die Sprachwahl wird global im Adminbereich gesetzt und gilt anschliessend fuer Admin und Public. Sie schreibt `de-DE` oder `en-GB` in `[general] language` der OpenRCT2-Konfiguration und startet einen laufenden Gameserver kontrolliert neu. Spielankuendigungen stammen bereits gerendert aus OpenRCT2 und folgen dadurch derselben Runtime-Sprache.

## Datenschutz und Git

Dieses Repository enthaelt **keine** RCT2-Originaldaten, Saves, Autosaves, Backups, Screenshots, hochgeladenen Logos, Adminpasswoerter oder Session-Secrets. Diese Daten liegen ausschliesslich unter `data/` oder in `.env` und sind per `.gitignore` ausgeschlossen.

Das Repository enthaelt nur das versionierte Standardlogo unter `admin/static/openrct2-server-logo.png`. Alle weiteren Logos werden im Adminbereich hochgeladen und lokal gespeichert.

## Voraussetzungen

- Alpine-LXC mit Docker-Nesting, mindestens 2 vCPU und 2 GB RAM.
- Git-Repository-URL und ein sicheres Adminpasswort.
- HTTP-Reverse-Proxy auf `<LXC-IP>:8088`.
- Direkte TCP-Weiterleitung von `11753` auf den LXC fuer OpenRCT2-Clients. Ein HTTP-Reverse-Proxy transportiert kein Multiplayer-Protokoll.

## Neuinstallation im LXC

Als `root` im LXC:

```sh
apk add git
git clone <repository-url> /tmp/openrct2-admin
ADMIN_PASSWORD='<starkes-passwort>' /tmp/openrct2-admin/deploy/install-alpine-lxc.sh /opt/openrct2-admin <repository-url>
```

Danach `/admin` oeffnen und den Wizard abschliessen:

1. RCT2-Originaldaten als ZIP hochladen.
2. `.sv6`- oder `.park`-Save hochladen.
3. Website, Servername, Passwort und Public-Freigaben setzen.
4. Gameserver starten.

Die nicht versionierte `.env` kann erweitert werden:

```dotenv
PUBLIC_HOST=openrct2.example.com
PUBLIC_ADDRESS_URL=https://api.ipify.org
PUBLIC_ADDRESS_REFRESH_SECONDS=300
PROJECT_URL=https://github.com/bripon76/openrct2-dedicated-server
```

Die DDNS-/OpenRCT2-Werbeadresse im Bereich **Server und Website** wird als `advertise_address` in `[network]` gespeichert. Erlaubt sind ein Hostname, IPv4 oder eine geklammerte IPv6-Adresse, jeweils optional mit Port, etwa `park.example.org`, `203.0.113.10:11753` oder `[2001:db8::10]:11753`. URLs, Pfade und Steuerzeichen werden abgewiesen. Das Speichern startet einen laufenden Gameserver einmal kontrolliert neu und die Adresse hat auf der Public-Seite Vorrang vor der bisherigen reinen Anzeigeadresse und der externen Ermittlung.

Wenn keine Werbeadresse und keine manuelle Anzeigeadresse gesetzt sind, fragt die Verwaltung `PUBLIC_ADDRESS_URL` mit kurzem Timeout ab, akzeptiert ausschliesslich IPv4 und cached das Ergebnis fuer `PUBLIC_ADDRESS_REFRESH_SECONDS`. Bei Fehlern wird `PUBLIC_HOST` verwendet. Die angezeigte Multiplayer-Adresse erhaelt immer Port `11753`.

Abstuerze eines Gameclients beim Verbinden lassen sich nicht allein anhand der IP-Adresse diagnostizieren. Dafuer werden die Server- und Client-Logs benoetigt.

## Bestehenden LXC auf Git umstellen

Die folgenden Befehle ersetzen nur versionierte Programmdateien. `data/` und `.env` bleiben erhalten.

```sh
cd /opt/openrct2-admin
git init -b master
git remote add origin <repository-url>
git fetch origin master
git reset --hard origin/master
./deploy/update-alpine-lxc.sh
```

## Update aus Git

Nach jedem Push:

```sh
/opt/openrct2-admin/deploy/update-alpine-lxc.sh
```

Das Skript ruft `origin/master` ab, baut den Admincontainer neu und erstellt den Gameserver mit der gewaehlten OpenRCT2-Version neu. Lief der Server vorher, startet er anschliessend wieder. Ein separates `git pull` ist nicht erforderlich.

Status und Remote pruefen:

```sh
cd /opt/openrct2-admin
git log -1 --oneline
git status --short
git remote -v
docker compose ps
```

## Mehrere Parks

Ein Gameserver hostet genau einen Park, kann aber mehrere Spieler bedienen. Fuer mehrere parallele Parks wird ein LXC pro Park empfohlen: getrennte Laufzeitdaten, eigener Adminzugang und eigener externer TCP-Port.

## Pruefungen

```sh
python3 -m py_compile admin/app.py
docker compose config
docker compose ps
docker compose logs admin
```
