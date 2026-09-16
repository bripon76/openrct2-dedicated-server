from flask import Flask, Response, jsonify, request, send_from_directory, session, redirect, stream_with_context
import configparser, ipaddress, json, os, socket, time, secrets, pathlib, zipfile, shutil, tempfile, shlex, threading, random, tarfile, io, re, urllib.request

try:
    import docker
except Exception:
    docker = None


def write_active_save_marker(filename):
    os.makedirs(SAVE_DIR, exist_ok=True)
    active_file = os.environ.get("ACTIVE_SAVE_FILE", os.path.join(SAVE_DIR, ".active-save"))
    tmp = active_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(filename.strip() + "\n")
    os.replace(tmp, active_file)

def read_active_save_marker():
    active_file = os.environ.get("ACTIVE_SAVE_FILE", os.path.join(SAVE_DIR, ".active-save"))
    try:
        with open(active_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _list_save_files():
    os.makedirs(SAVE_DIR, exist_ok=True)
    result = []
    for name in sorted(os.listdir(SAVE_DIR)):
        p = os.path.join(SAVE_DIR, name)
        if os.path.isfile(p) and name.lower().endswith((".sv6", ".park")):
            result.append(name)
    return result

def setup_state():
    pf = server_preflight()
    return {
        "ready": bool(pf.get("ready")),
        "preflight": pf,
        "saves": list_saves(),
        "active_save": get_active_save(),
        "runtime": runtime_state(),
    }

def _docker_client():
    try:
        import docker
        return docker.from_env(timeout=int(os.getenv('DOCKER_API_TIMEOUT', '120')))
    except Exception:
        return None

def _container_state():
    client = _docker_client()
    if not client:
        return {"known": False, "status": "unknown"}
    try:
        c = client.containers.get(os.environ.get("GAME_CONTAINER", "openrct2-server"))
        c.reload()
        return {"known": True, "status": c.status}
    except Exception:
        return {"known": True, "status": "not_created"}

def _ensure_game_container_created():
    # Docker Compose profiles mean the container might not yet exist.
    client = _docker_client()
    if not client:
        raise RuntimeError("Docker API unavailable")
    name = os.environ.get("GAME_CONTAINER", "openrct2-server")
    try:
        return client.containers.get(name)
    except Exception:
        raise RuntimeError(
            "Game container not created yet. Run once: "
            "docker compose -f docker-compose.live-mac.yml --profile game create openrct2"
        )


def replace_directory_contents_mount_safe(src_dir, dst_dir):
    """
    Replace contents of a bind-mounted destination directory without renaming
    the mount point itself. This avoids EBUSY on Docker bind mounts.
    """
    os.makedirs(dst_dir, exist_ok=True)

    # Remove current contents, but never the destination directory itself.
    for name in os.listdir(dst_dir):
        p = os.path.join(dst_dir, name)
        try:
            if os.path.islink(p) or os.path.isfile(p):
                os.unlink(p)
            elif os.path.isdir(p):
                shutil.rmtree(p)
        except FileNotFoundError:
            pass

    # Move/copy validated payload into the mounted directory.
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        if os.path.isdir(src) and not os.path.islink(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv('SESSION_SECRET', secrets.token_hex(32))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme')
ADMIN_PASSWORD_FILE = os.getenv('ADMIN_PASSWORD_FILE', '/data/config/.admin-password')
SAVE_DIR = os.getenv('SAVE_DIR', '/data/save')
ACTIVE_SAVE_FILE = os.getenv('ACTIVE_SAVE_FILE', os.path.join(SAVE_DIR, '.active-save'))
BRIDGE_HOST = os.getenv('BRIDGE_HOST', '127.0.0.1')
BRIDGE_PORT = int(os.getenv('BRIDGE_PORT', '11754'))
MOCK = os.getenv('MOCK_MODE', 'true').lower() in ('1','true','yes')
CONTROL_MODE = os.getenv('CONTROL_MODE', 'mock' if MOCK else 'docker').lower()
GAME_CONTAINER = os.getenv('GAME_CONTAINER', 'openrct2-server')
CONFIG_FILE = os.getenv('OPENRCT2_CONFIG', '/data/config/config.ini')
RCT2_DATA_DIR = os.getenv('RCT2_DATA_DIR', '/data/rct2')
MANIFEST_FILE = os.getenv('RCT2_MANIFEST_FILE', os.path.join(os.path.dirname(__file__), 'rct2-required-files.json'))
SCREENSHOT_DIR = os.getenv('SCREENSHOT_DIR', '/data/config/screenshot')
OPENRCT2_VERSION = os.getenv('OPENRCT2_VERSION', '0.5.5')
PUBLIC_HOST = os.getenv('PUBLIC_HOST', 'openrct2.example.com')
PUBLIC_ADDRESS_URL = os.getenv('PUBLIC_ADDRESS_URL', 'https://api.ipify.org')
PUBLIC_ADDRESS_REFRESH_SECONDS = max(1, int(os.getenv('PUBLIC_ADDRESS_REFRESH_SECONDS', '300')))
PUBLIC_ADDRESS_TIMEOUT = max(1, int(os.getenv('PUBLIC_ADDRESS_TIMEOUT_SECONDS', '3')))
PUBLIC_ADDRESS_CACHE = {'address': '', 'expires': 0.0}
PROJECT_URL = os.getenv('PROJECT_URL', 'https://github.com/bripon76/openrct2-dedicated-server')
MAP_VIEW_COUNT = 4
MAP_HISTORY_LIMIT = 20
MAP_REFRESH_SECONDS = int(os.getenv('MAP_REFRESH_SECONDS', '300'))
MAP_CAPTURE_LOCK = threading.Lock()
BACKUP_DIR = os.getenv('BACKUP_DIR', '/data/config/backup')
BACKUP_LIMIT = 7
IMAGE_SELECTION_FILE = os.getenv('OPENRCT2_IMAGE_FILE', '/data/config/.openrct2-image')
IMAGE_REPOSITORY = 'openrct2/openrct2-cli'
IMAGE_TAG_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')
IMAGE_REQUEST_TIMEOUT = 10
WEB_SETTINGS_FILE = os.getenv('WEB_SETTINGS_FILE', '/data/config/admin-settings.json')
BRANDING_DIR = os.getenv('BRANDING_DIR', '/data/config/branding')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_BYTES', str(1024 * 1024 * 1024)))

MOCK_STATE = {
    'server': {
        'online': True, 'state': 'running', 'version': '0.5.5',
        'name': 'OpenRCT2 Testserver', 'park': 'OpenRCT2 Park',
        'uptime': '2h 41m', 'port': 11753, 'address': 'localhost:11753',
        'maxPlayers': 10, 'description': 'OpenRCT2 Multiplayer Testserver'
    },
    'map': {'available': True, 'image': '/static/park-demo.svg', 'updated': 'Demo-Stand', 'download': '/downloads/current'},
    'downloads': {'openrct2': 'https://openrct2.io/', 'park': '/downloads/current'},
    'defaultGroup': 2,
    'groups': [
        {'id': 0, 'name': 'Admin', 'permissions': ['chat','terraform','set_water_level','toggle_pause','create_ride','remove_ride','build_ride','ride_properties','scenery','path','clear_landscape','guest','staff','park_properties','park_funding','kick_player','modify_groups','set_player_group','cheat','toggle_scenery_cluster','passwordless_login','modify_tile','edit_scenario_options']},
        {'id': 1, 'name': 'Spectator', 'permissions': ['chat']},
        {'id': 2, 'name': 'Builder', 'permissions': ['chat','create_ride','build_ride','ride_properties','scenery','path','guest','staff']},
    ],
    'players': [
        {'id': 7, 'name': 'Player01', 'group': 2, 'ping': 31, 'commandsRan': 94, 'moneySpent': 32870},
        {'id': 9, 'name': 'Gast123', 'group': 1, 'ping': 48, 'commandsRan': 2, 'moneySpent': 0},
    ]
}

PERMISSIONS = ['chat','terraform','set_water_level','toggle_pause','create_ride','remove_ride','build_ride','ride_properties','scenery','path','clear_landscape','guest','staff','park_properties','park_funding','kick_player','modify_groups','set_player_group','cheat','toggle_scenery_cluster','passwordless_login','modify_tile','edit_scenario_options']

def current_admin_password():
    try:
        return pathlib.Path(ADMIN_PASSWORD_FILE).read_text(encoding='utf-8').strip() or ADMIN_PASSWORD
    except FileNotFoundError:
        return ADMIN_PASSWORD

def set_admin_password(password):
    path = pathlib.Path(ADMIN_PASSWORD_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(password, encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)

def bridge_call(payload):
    if CONTROL_MODE == 'docker':
        request_line = json.dumps(payload) + '\n'
        command = (
            "exec 3<>/dev/tcp/127.0.0.1/11754; "
            f"printf %s {shlex.quote(request_line)} >&3; "
            "IFS= read -r -t 2 response <&3; printf %s \"$response\""
        )
        result = docker_container().exec_run(['/bin/bash', '-c', command])
        if result.exit_code != 0:
            error = result.output.decode('utf-8', errors='replace').strip()
            raise RuntimeError(error or 'Admin-Bridge im Gameserver nicht erreichbar')
        return json.loads(result.output.decode('utf-8'))

    with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=2) as s:
        s.sendall((json.dumps(payload) + '\n').encode())
        data = b''
        while b'\n' not in data:
            chunk = s.recv(65536)
            if not chunk: break
            data += chunk
        if not data:
            raise RuntimeError('empty bridge response')
        return json.loads(data.split(b'\n',1)[0].decode())

def docker_container():
    if docker is None:
        raise RuntimeError('docker SDK not installed')
    client = docker.from_env(timeout=int(os.getenv('DOCKER_API_TIMEOUT', '120')))
    return client.containers.get(GAME_CONTAINER)

def runtime_state():
    if MOCK:
        return MOCK_STATE['server']['state']
    if CONTROL_MODE != 'docker':
        return 'unknown'
    try:
        c = docker_container(); c.reload(); return c.status
    except Exception:
        return 'stopped'

def read_web_settings():
    try:
        raw = json.loads(pathlib.Path(WEB_SETTINGS_FILE).read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            return {}
        keys = ('site_title', 'admin_footer_text', 'public_footer_text', 'server_address', 'public_info_title', 'public_info_text', 'public_show_server_details', 'public_show_park_views', 'public_show_players', 'public_show_park_stats', 'public_show_announcements', 'ui_language')
        return {key: str(raw[key]).replace('\r', '')[:1000] for key in keys if key in raw}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def write_web_settings(values):
    path = pathlib.Path(WEB_SETTINGS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = read_web_settings()
    merged.update({key: str(value).replace('\r', '')[:1000 if key == 'public_info_text' else 256] for key, value in values.items()})
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(merged, ensure_ascii=True, sort_keys=True) + '\n', encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)

def read_network_settings():
    values = {'server_name':'', 'server_description':'', 'server_greeting':'', 'maxplayers':'10', 'advertise':'false', 'default_password':'', 'site_title':'OpenRCT2 Server', 'admin_footer_text':'', 'public_footer_text':'', 'server_address':'', 'public_info_title':'', 'public_info_text':'', 'public_show_server_details':'true', 'public_show_park_views':'true', 'public_show_players':'true', 'public_show_park_stats':'true', 'public_show_announcements':'false', 'ui_language':'de'}
    if MOCK:
        values.update({'server_name': MOCK_STATE['server']['name'], 'server_description': MOCK_STATE['server']['description'], 'server_greeting':'Willkommen!', 'maxplayers': str(MOCK_STATE['server']['maxPlayers']), 'advertise':'false'})
        values.update(read_web_settings())
        return values
    if not os.path.exists(CONFIG_FILE):
        values.update(read_web_settings())
        return values
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(CONFIG_FILE)
    if cfg.has_section('network'):
        for k in values:
            if k in ('site_title', 'admin_footer_text', 'public_footer_text', 'server_address', 'public_info_title', 'public_info_text', 'public_show_server_details', 'public_show_park_views', 'public_show_players', 'public_show_park_stats', 'public_show_announcements', 'ui_language'): continue
            if cfg.has_option('network', k): values[k] = cfg.get('network', k).strip('"')
    if cfg.has_option('openrct2_admin', 'site_title'):
        values['site_title'] = cfg.get('openrct2_admin', 'site_title').strip('"')
    for key in ('admin_footer_text', 'public_footer_text', 'server_address', 'public_info_title', 'public_info_text', 'public_show_server_details', 'public_show_park_views', 'public_show_players', 'public_show_park_stats', 'public_show_announcements', 'ui_language'):
        if cfg.has_option('openrct2_admin', key):
            values[key] = cfg.get('openrct2_admin', key).strip('"')
    values.update(read_web_settings())
    return values

def write_network_settings(payload):
    allowed = {'server_name','server_description','server_greeting','maxplayers','advertise','default_password','site_title','admin_footer_text','public_footer_text','server_address','public_info_title','public_info_text','public_show_server_details','public_show_park_views','public_show_players','public_show_park_stats','public_show_announcements','ui_language'}
    web_keys = {'site_title', 'admin_footer_text', 'public_footer_text', 'server_address', 'public_info_title', 'public_info_text', 'public_show_server_details', 'public_show_park_views', 'public_show_players', 'public_show_park_stats', 'public_show_announcements', 'ui_language'}
    if MOCK:
        if 'server_name' in payload: MOCK_STATE['server']['name'] = str(payload['server_name'])[:64]
        if 'server_description' in payload: MOCK_STATE['server']['description'] = str(payload['server_description'])[:256]
        if 'maxplayers' in payload: MOCK_STATE['server']['maxPlayers'] = max(1, min(255, int(payload['maxplayers'])))
        write_web_settings({key: payload[key] for key in web_keys if key in payload})
        return read_network_settings()
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    if os.path.exists(CONFIG_FILE): cfg.read(CONFIG_FILE)
    if not cfg.has_section('network'): cfg.add_section('network')
    for k,v in payload.items():
        if k not in allowed: continue
        if k == 'ui_language':
            if not cfg.has_section('general'): cfg.add_section('general')
            cfg.set('general', 'language', 'en-GB' if str(v) == 'en' else 'de-DE')
            continue
        if k in ('site_title', 'admin_footer_text', 'public_footer_text'):
            if not cfg.has_section('openrct2_admin'): cfg.add_section('openrct2_admin')
            cfg.set('openrct2_admin', k, str(v).replace('\n',' ')[:256])
            continue
        if k == 'maxplayers': v = str(max(1, min(255, int(v))))
        elif k == 'advertise': v = 'true' if str(v).lower() in ('1','true','yes','on') else 'false'
        else: v = str(v).replace('\n',' ')[:256]
        cfg.set('network', k, v)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f: cfg.write(f, space_around_delimiters=True)
    web_values = {key: payload[key] for key in web_keys if key in payload}
    if web_values:
        write_web_settings(web_values)
    return read_network_settings()

def branding_logo_url():
    for extension in ('.png', '.jpg', '.jpeg', '.webp'):
        path = pathlib.Path(BRANDING_DIR) / f'logo{extension}'
        if path.is_file():
            return f'/branding/logo?updated={int(path.stat().st_mtime)}'
    return '/static/openrct2-server-logo.png'

def _address_with_port(host):
    host = str(host or '').strip()
    if not host:
        return ''
    try:
        address = ipaddress.ip_address(host.strip('[]'))
        return f'[{address}]:11753' if address.version == 6 else f'{address}:11753'
    except ValueError:
        pass
    # Keep an explicitly configured hostname:port unchanged.
    if re.fullmatch(r'(?:[^:\[\]]+|\[[^\]]+\]):\d{1,5}', host):
        return host
    return f'{host}:11753'

def public_server_address(override):
    if str(override or '').strip():
        return _address_with_port(override)
    now = time.monotonic()
    if now >= PUBLIC_ADDRESS_CACHE['expires']:
        try:
            request_object = urllib.request.Request(PUBLIC_ADDRESS_URL, headers={'User-Agent': 'openrct2-admin'})
            with urllib.request.urlopen(request_object, timeout=PUBLIC_ADDRESS_TIMEOUT) as response:
                candidate = response.read(64).decode('ascii', errors='ignore').strip()
            if ipaddress.ip_address(candidate).version != 4:
                raise ValueError('public address service did not return IPv4')
            PUBLIC_ADDRESS_CACHE['address'] = candidate
        except Exception as error:
            app.logger.warning('Public IPv4 discovery failed: %s', error)
        PUBLIC_ADDRESS_CACHE['expires'] = now + PUBLIC_ADDRESS_REFRESH_SECONDS
    return _address_with_port(PUBLIC_ADDRESS_CACHE['address'] or PUBLIC_HOST)

def setup_status():
    data = rct2_data_status()
    active_save = get_active_save()
    completed = False
    if os.path.exists(CONFIG_FILE):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(CONFIG_FILE)
        completed = cfg.getboolean('openrct2_admin', 'setup_completed', fallback=False)
    return {
        'complete': completed or (os.path.exists(CONFIG_FILE) and bool(data.get('complete')) and bool(active_save)),
        'rct2_ready': bool(data.get('complete')),
        'active_save': active_save,
        'save_ready': bool(active_save),
    }

def complete_setup(payload):
    status = setup_status()
    if not status['rct2_ready'] or not status['save_ready']:
        raise ValueError('Originaldaten und ein aktiver Spielstand werden benötigt')
    settings = write_network_settings(payload)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    if os.path.exists(CONFIG_FILE):
        cfg.read(CONFIG_FILE)
    if not cfg.has_section('openrct2_admin'):
        cfg.add_section('openrct2_admin')
    cfg.set('openrct2_admin', 'setup_completed', 'true')
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        cfg.write(f, space_around_delimiters=True)
    return settings

def map_images():
    images = []
    for index in range(MAP_VIEW_COUNT):
        name = f'server-map-{index}.png'
        path = os.path.join(SCREENSHOT_DIR, name)
        if os.path.isfile(path):
            images.append({'index': index, 'image': f'/map/{index}.png?t={int(os.path.getmtime(path))}'})
    return images

def current_runtime_save():
    active = pathlib.Path(SAVE_DIR) / get_active_save()
    latest = _latest_autosave()
    if latest and (not active.exists() or latest.stat().st_mtime > active.stat().st_mtime):
        return latest
    return active

def capture_map_views():
    preflight = server_preflight()
    if not preflight.get('ready'):
        raise RuntimeError('; '.join(preflight.get('reasons') or ['Preflight nicht erfüllt']))
    if MOCK or CONTROL_MODE != 'docker':
        raise RuntimeError('Kartenaufnahme ist nur im Docker-Livebetrieb verfügbar')

    with MAP_CAPTURE_LOCK:
        runtime_save = current_runtime_save()
        if not runtime_save.is_file():
            raise RuntimeError('Kein aktueller Spielstand für die Kartenaufnahme verfügbar')
        game_save = '/home/openrct2/.config/OpenRCT2/save/' + str(runtime_save.relative_to(SAVE_DIR))
        client = docker_container()
        client.exec_run(['openrct2-cli', 'set-rct2', '/rct2'], environment={'HOME': '/home/openrct2'})
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        for index in range(MAP_VIEW_COUNT):
            x = random.randint(512, 3584)
            y = random.randint(512, 3584)
            zoom = random.choice((0, 1, 2))
            rotation = random.randint(0, 3)
            game_output = f'/home/openrct2/.config/OpenRCT2/screenshot/server-map-{index}.png'
            result = client.exec_run([
                'openrct2-cli', 'screenshot', game_save, game_output,
                '1280', '720', str(x), str(y), '0', str(zoom), str(rotation), '--no-peeps'
            ], environment={'HOME': '/home/openrct2'})
            if result.exit_code != 0:
                error = result.output.decode('utf-8', errors='replace').strip()
                raise RuntimeError(error or f'Ansicht {index + 1} konnte nicht erzeugt werden')

        shutil.copy2(os.path.join(SCREENSHOT_DIR, 'server-map-0.png'), os.path.join(SCREENSHOT_DIR, 'server-map.png'))
        history_dir = os.path.join(SCREENSHOT_DIR, 'history')
        os.makedirs(history_dir, exist_ok=True)
        timestamp = int(time.time())
        for index in range(MAP_VIEW_COUNT):
            shutil.copy2(
                os.path.join(SCREENSHOT_DIR, f'server-map-{index}.png'),
                os.path.join(history_dir, f'snapshot-{timestamp}-{index}.png')
            )
        history = sorted(
            (entry for entry in pathlib.Path(history_dir).glob('snapshot-*.png') if entry.is_file()),
            key=lambda entry: entry.stat().st_mtime
        )
        for entry in history[:-MAP_HISTORY_LIMIT]:
            entry.unlink()
        return map_images()

def _periodic_map_refresh():
    while True:
        time.sleep(MAP_REFRESH_SECONDS)
        if runtime_state() != 'running':
            continue
        try:
            capture_map_views()
        except Exception as error:
            app.logger.warning('Periodic park snapshot failed: %s', error)

threading.Thread(target=_periodic_map_refresh, name='park-snapshot-refresh', daemon=True).start()

def state():
    if MOCK:
        out = json.loads(json.dumps(MOCK_STATE))
        out['server']['address'] = public_server_address(read_network_settings().get('server_address'))
        out['mock'] = True
        return out

    settings = read_network_settings()
    runtime = runtime_state()
    out = {
        'ok': True,
        'mock': False,
        'server': {
            'online': runtime == 'running',
            'state': runtime,
            'version': f'OpenRCT2 {selected_game_version()}',
            'name': settings.get('server_name') or 'OpenRCT2 Server',
            'description': settings.get('server_description', ''),
            'maxPlayers': int(settings.get('maxplayers') or 10),
            'port': 11753,
            'address': public_server_address(settings.get('server_address')),
        },
        'players': [],
        'siteTitle': settings.get('site_title') or 'OpenRCT2 Server',
        'adminFooterText': settings.get('admin_footer_text', ''),
        'publicFooterText': settings.get('public_footer_text', ''),
        'projectUrl': PROJECT_URL,
        'logoUrl': branding_logo_url(),
        'publicInfoTitle': settings.get('public_info_title', ''),
        'publicInfoText': settings.get('public_info_text', ''),
        'publicShowServerDetails': str(settings.get('public_show_server_details', 'true')).lower() == 'true',
        'publicShowParkViews': str(settings.get('public_show_park_views', 'true')).lower() == 'true',
        'publicShowPlayers': str(settings.get('public_show_players', 'true')).lower() == 'true',
        'publicShowParkStats': str(settings.get('public_show_park_stats', 'true')).lower() == 'true',
        'publicShowAnnouncements': str(settings.get('public_show_announcements', 'false')).lower() == 'true',
        'uiLanguage': settings.get('ui_language', 'de'),
    }
    try:
        bridge_status = bridge_call({'cmd':'status'})
        out.update(bridge_status)
    except Exception as e:
        out['bridgeUnavailable'] = str(e)

    out.setdefault('server', {})
    out['server'].update({
        'online': runtime == 'running',
        'state': runtime,
        'name': settings.get('server_name') or out['server'].get('name', 'OpenRCT2 Server'),
        'description': settings.get('server_description', ''),
        'maxPlayers': int(settings.get('maxplayers') or 10),
        'port': 11753,
        'address': public_server_address(settings.get('server_address')),
        'version': f'OpenRCT2 {selected_game_version()}',
    })
    shot = os.path.join(SCREENSHOT_DIR, 'server-map.png')
    images = map_images()
    if os.path.exists(shot):
        updated = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(shot)))
        out['map'] = {'available':True,'image':'/map/current.png?t='+str(int(os.path.getmtime(shot))),'images':images,'updated':updated}
    else:
        out.setdefault('map', {'available': False, 'image': '/static/park-demo.svg', 'images':images, 'updated': 'noch nicht erzeugt'})
    out.setdefault('downloads', {'openrct2': 'https://openrct2.io/'})
    return out



def _required_rct2_files():
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('required', [])
    except Exception:
        return []


def _relative_game_files(root):
    root = pathlib.Path(root)
    found = set()
    for folder in ('Data', 'ObjData'):
        d = root / folder
        if not d.exists():
            continue
        for x in d.rglob('*'):
            if x.is_file():
                found.add((folder + '/' + str(x.relative_to(d))).replace('\\','/').lower())
    return found


def validate_rct2_tree(root):
    required = _required_rct2_files()
    found = _relative_game_files(root)
    missing = [x for x in required if x.lower() not in found]
    data_count = sum(1 for x in found if x.startswith('data/'))
    obj_count = sum(1 for x in found if x.startswith('objdata/') and x.endswith('.dat'))
    return {
        'installed': len(required) > 0 and not missing,
        'complete': len(required) > 0 and not missing,
        'requiredFiles': len(required),
        'foundRequiredFiles': len(required) - len(missing),
        'missingCount': len(missing),
        'missing': missing[:100],
        'missingTruncated': len(missing) > 100,
        'dataFiles': data_count,
        'objDataFiles': obj_count,
        'path': str(root),
        'message': ('RCT2-Originaldaten vollständig geprüft' if required and not missing else ('Prüfmanifest fehlt' if not required else f'{len(missing)} benötigte Dateien fehlen'))
    }


def rct2_data_status():
    return validate_rct2_tree(RCT2_DATA_DIR)

def _zip_members_under_root(zf):
    names=[]
    for info in zf.infolist():
        raw=info.filename.replace('\\','/')
        if not raw or raw.startswith('/') or '..' in pathlib.PurePosixPath(raw).parts:
            raise ValueError('Unsicherer ZIP-Pfad erkannt')
        if raw.startswith('__MACOSX/') or raw.endswith('/.DS_Store') or raw.endswith('.DS_Store'):
            continue
        names.append((info, raw))
    return names


def _find_game_root(extracted):
    extracted=pathlib.Path(extracted)
    candidates=[extracted]
    candidates += [p for p in extracted.rglob('*') if p.is_dir() and p.relative_to(extracted).parts and len(p.relative_to(extracted).parts) <= 3]
    for p in candidates:
        data = next((x for x in p.iterdir() if x.is_dir() and x.name.lower()=='data'), None) if p.exists() else None
        obj = next((x for x in p.iterdir() if x.is_dir() and x.name.lower()=='objdata'), None) if p.exists() else None
        if data and obj:
            check = validate_rct2_tree(p)
            if check['complete']:
                return p
    raise ValueError('RCT2-Daten sind unvollständig: Die ZIP enthält nicht alle benötigten Referenzdateien.')


def install_rct2_zip(file_storage):
    os.makedirs('/tmp/rct2-upload', exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rct2-', dir='/tmp/rct2-upload') as td:
        zip_path=pathlib.Path(td)/'original-data.zip'
        file_storage.save(zip_path)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                members=_zip_members_under_root(zf)
                total=sum(i.file_size for i,_ in members)
                if total > 3 * 1024 * 1024 * 1024:
                    raise ValueError('Entpackte Daten sind zu groß')
                for info, raw in members:
                    out=pathlib.Path(td)/'extract'/raw
                    if info.is_dir():
                        out.mkdir(parents=True, exist_ok=True)
                        continue
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(out,'wb') as dst:
                        shutil.copyfileobj(src,dst)
        except zipfile.BadZipFile:
            raise ValueError('Datei ist kein gültiges ZIP-Archiv')
        game_root=_find_game_root(pathlib.Path(td)/'extract')
        target=pathlib.Path(RCT2_DATA_DIR)
        stage=target.with_name(target.name+'.new')

        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True, exist_ok=True)
        for name in ('Data','ObjData'):
            src=next(x for x in game_root.iterdir() if x.is_dir() and x.name.lower()==name.lower())
            shutil.copytree(src, stage/name, dirs_exist_ok=True)
        # Optional useful folders if present in a full installation.
        for optional in ('Scenarios','Tracks','Saved Games','Landscapes'):
            src=next((x for x in game_root.iterdir() if x.is_dir() and x.name.lower()==optional.lower()), None)
            if src: shutil.copytree(src, stage/optional, dirs_exist_ok=True)
        replace_directory_contents_mount_safe(str(stage), str(target))
    return rct2_data_status()


def server_preflight():
    data = rct2_data_status()
    active = get_active_save()
    save_ok = bool(active and os.path.isfile(os.path.join(SAVE_DIR, active)) and allowed_save(active))
    reasons=[]
    if not data.get('complete'):
        reasons.append('RCT2-Originaldaten unvollständig')
    if not save_ok:
        reasons.append('Kein gültiger aktiver Spielstand (.sv6/.park)')
    return {'ready': not reasons, 'rct2Data': data, 'active_save': active, 'saveReady': save_ok, 'reasons': reasons}

def require_admin(fn):
    from functools import wraps
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('admin'):
            if request.path.startswith('/api/'):
                return jsonify({'ok':False,'error':'authentication required'}), 401
            return redirect('/login')
        return fn(*args, **kwargs)
    return wrapped

def allowed_save(filename):
    return pathlib.Path(filename).suffix.lower() in ('.sv6', '.park')

def safe_save_name(filename):
    name = pathlib.Path(filename).name
    return ''.join(c for c in name if c.isalnum() or c in ' ._-()[]')[:180]

def list_saves():
    os.makedirs(SAVE_DIR, exist_ok=True)
    active = get_active_save()
    out=[]
    for f in os.listdir(SAVE_DIR):
        path=os.path.join(SAVE_DIR,f)
        if os.path.isfile(path) and allowed_save(f):
            st=os.stat(path)
            out.append({'name':f,'size':st.st_size,'modified':int(st.st_mtime),'active':f==active})
    return sorted(out, key=lambda x:x['modified'], reverse=True)

def _latest_autosave():
    autosave_dir = pathlib.Path(SAVE_DIR) / 'autosave'
    candidates = [entry for entry in autosave_dir.glob('*') if entry.is_file() and allowed_save(entry.name)]
    return max(candidates, key=lambda entry: entry.stat().st_mtime) if candidates else None

def list_backups():
    backup_dir = pathlib.Path(BACKUP_DIR)
    if not backup_dir.exists():
        return []
    result = []
    for entry in backup_dir.glob('backup-*.tar.gz'):
        if entry.is_file():
            result.append({'name': entry.name, 'size': entry.stat().st_size, 'modified': int(entry.stat().st_mtime)})
    return sorted(result, key=lambda item: item['modified'], reverse=True)

def create_backup():
    source = _latest_autosave()
    if source is None:
        active = get_active_save()
        if not active:
            raise RuntimeError('Kein Spielstand für das Backup verfügbar')
        source = pathlib.Path(SAVE_DIR) / active
    backup_dir = pathlib.Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    filename = f"backup-{time.strftime('%Y-%m-%d')}.tar.gz"
    target = backup_dir / filename
    temporary = backup_dir / f'.{filename}.tmp'
    with tarfile.open(temporary, 'w:gz') as archive:
        archive.add(CONFIG_FILE, arcname='config.ini')
        archive.add(source, arcname=f'save/{source.name}')
        metadata = json.dumps({'save': source.name}, ensure_ascii=True).encode('utf-8')
        info = tarfile.TarInfo('metadata.json')
        info.size = len(metadata)
        archive.addfile(info, fileobj=io.BytesIO(metadata))
    os.replace(temporary, target)
    backups = list_backups()
    for backup in backups[BACKUP_LIMIT:]:
        (backup_dir / backup['name']).unlink()
    return list_backups()

def backup_file(name):
    basename = pathlib.Path(name).name
    if basename != name or not re.fullmatch(r'backup-[^/]+\.tar\.gz', basename):
        return None
    path = pathlib.Path(BACKUP_DIR) / basename
    return path if path.is_file() else None

def selected_game_image():
    try:
        image = pathlib.Path(IMAGE_SELECTION_FILE).read_text(encoding='utf-8').strip()
        if image.startswith(IMAGE_REPOSITORY + ':') and IMAGE_TAG_PATTERN.fullmatch(image.rsplit(':', 1)[1]):
            return image
    except FileNotFoundError:
        pass
    return os.getenv('OPENRCT2_IMAGE', f'{IMAGE_REPOSITORY}:{OPENRCT2_VERSION}')

def selected_game_version():
    return selected_game_image().rsplit(':', 1)[-1]

def available_game_versions():
    url = f'https://hub.docker.com/v2/repositories/{IMAGE_REPOSITORY}/tags?page_size=100'
    request_object = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'openrct2-admin'})
    try:
        with urllib.request.urlopen(request_object, timeout=IMAGE_REQUEST_TIMEOUT) as response:
            payload = json.load(response)
    except Exception as error:
        raise RuntimeError(f'Versionsliste konnte nicht geladen werden: {error}')
    versions = sorted({item.get('name', '') for item in payload.get('results', []) if IMAGE_TAG_PATTERN.fullmatch(item.get('name', ''))}, key=lambda value: tuple(map(int, value.split('.'))), reverse=True)
    if not versions:
        raise RuntimeError('Keine stabilen OpenRCT2-Versionen gefunden')
    return versions

def _game_container_definition(container):
    container.reload()
    attrs = container.attrs
    config = attrs['Config']
    networks = attrs['NetworkSettings'].get('Networks') or {}
    client = container.client
    networking_config = client.api.create_networking_config({name: client.api.create_endpoint_config(aliases=settings.get('Aliases')) for name, settings in networks.items()}) if networks else None
    return {
        'was_running': container.status == 'running', 'image': config['Image'],
        'kwargs': {
            'hostname': config.get('Hostname'), 'user': config.get('User'), 'tty': config.get('Tty'),
            'open_stdin': config.get('OpenStdin'), 'stdin_once': config.get('StdinOnce'), 'environment': config.get('Env'),
            'labels': config.get('Labels'), 'stop_signal': config.get('StopSignal'), 'stop_timeout': config.get('StopTimeout'),
            'healthcheck': config.get('Healthcheck'), 'entrypoint': config.get('Entrypoint'), 'working_dir': config.get('WorkingDir'),
            'host_config': attrs['HostConfig'], 'networking_config': networking_config,
        }
    }

def _recreate_game_container(image, definition):
    client = _docker_client()
    if not client:
        raise RuntimeError('Docker API unavailable')
    try:
        container = client.containers.get(GAME_CONTAINER)
        container.reload()
        if container.status == 'running':
            container.stop(timeout=30)
        container.remove()
    except docker.errors.NotFound:
        pass
    created = client.api.create_container(image=image, name=GAME_CONTAINER, **definition['kwargs'])
    replacement = client.containers.get(created['Id'])
    if definition['was_running']:
        replacement.start()
        time.sleep(2)
        replacement.reload()
        if replacement.status != 'running':
            raise RuntimeError(f'Container start failed: {replacement.status}')
    return definition['was_running']

def update_game_image(version):
    if not isinstance(version, str) or not IMAGE_TAG_PATTERN.fullmatch(version):
        raise ValueError('Ungültige OpenRCT2-Version')
    if version not in available_game_versions():
        raise ValueError('Version ist nicht als stabile openrct2-cli-Version verfügbar')
    client = _docker_client()
    if not client:
        raise RuntimeError('Docker API unavailable')
    target_image = f'{IMAGE_REPOSITORY}:{version}'
    try:
        definition = _game_container_definition(client.containers.get(GAME_CONTAINER))
        create_backup()
        client.images.pull(target_image)
        was_running = _recreate_game_container(target_image, definition)
        path = pathlib.Path(IMAGE_SELECTION_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(target_image + '\n', encoding='utf-8')
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        return {'image': target_image, 'restarted': was_running}
    except Exception as error:
        try:
            if 'definition' not in locals():
                raise RuntimeError('Vorherige Container-Konfiguration konnte nicht gelesen werden')
            client.images.pull(definition['image'])
            _recreate_game_container(definition['image'], definition)
        except Exception as rollback_error:
            raise RuntimeError(f'Update fehlgeschlagen ({error}); Rollback fehlgeschlagen: {rollback_error}')
        raise RuntimeError(f'Update fehlgeschlagen; vorheriger Container wurde wiederhergestellt: {error}')

def restore_backup(name):
    backup_path = backup_file(name)
    if backup_path is None:
        raise ValueError('Backup nicht gefunden')
    with tempfile.TemporaryDirectory(prefix='restore-') as temporary:
        root = pathlib.Path(temporary)
        with tarfile.open(backup_path, 'r:gz') as archive:
            members = archive.getmembers()
            if any(member.name.startswith('/') or '..' in pathlib.PurePosixPath(member.name).parts for member in members):
                raise ValueError('Unsicheres Backup-Archiv')
            archive.extractall(root, members=members, filter='data')
        metadata = json.loads((root / 'metadata.json').read_text(encoding='utf-8'))
        save_name = safe_save_name(metadata.get('save', ''))
        save_path = root / 'save' / save_name
        config_path = root / 'config.ini'
        if not allowed_save(save_name) or not save_path.is_file() or not config_path.is_file():
            raise ValueError('Backup ist unvollständig')
        was_running = runtime_state() == 'running'
        if was_running:
            docker_container().stop(timeout=20)
        shutil.copy2(config_path, CONFIG_FILE)
        shutil.copy2(save_path, pathlib.Path(SAVE_DIR) / save_name)
        set_active_save(save_name)
        if was_running:
            docker_container().start()
    return {'active_save': save_name, 'restarted': was_running}

def _daily_backup_job():
    while True:
        try:
            today = f"backup-{time.strftime('%Y-%m-%d')}.tar.gz"
            if not (pathlib.Path(BACKUP_DIR) / today).exists():
                create_backup()
        except Exception as error:
            app.logger.warning('Daily backup failed: %s', error)
        time.sleep(3600)

threading.Thread(target=_daily_backup_job, name='daily-backup', daemon=True).start()

def get_active_save():
    try:
        n=pathlib.Path(ACTIVE_SAVE_FILE).read_text(encoding='utf-8').strip()
        if n and allowed_save(n) and os.path.exists(os.path.join(SAVE_DIR,n)):
            return n
    except Exception:
        pass

    # If there is exactly one save, make it truly active by writing the marker.
    files=[]
    if os.path.isdir(SAVE_DIR):
        files=sorted(f for f in os.listdir(SAVE_DIR) if allowed_save(f))
    if len(files) == 1:
        set_active_save(files[0])
        return files[0]
    return ''

def set_active_save(name):
    name=safe_save_name(name)
    if not allowed_save(name) or not os.path.isfile(os.path.join(SAVE_DIR,name)):
        raise ValueError('Spielstand nicht gefunden oder Dateityp nicht erlaubt')
    pathlib.Path(ACTIVE_SAVE_FILE).write_text(name, encoding='utf-8')
    return name

@app.get('/login')
def login_page():
    if session.get('admin'): return redirect('/admin')
    return send_from_directory(app.static_folder, 'login.html')

@app.post('/api/login')
def api_login():
    pw=(request.get_json(silent=True) or {}).get('password','')
    if secrets.compare_digest(str(pw), str(current_admin_password())):
        session['admin']=True
        return jsonify({'ok':True})
    return jsonify({'ok':False,'error':'Falsches Passwort'}), 401

@app.post('/api/logout')
def api_logout():
    session.clear(); return jsonify({'ok':True})

@app.post('/api/admin/password')
@require_admin
def api_admin_password():
    payload = request.get_json(force=True) or {}
    current = str(payload.get('current_password', ''))
    new = str(payload.get('new_password', ''))
    if not secrets.compare_digest(current, current_admin_password()):
        return jsonify({'ok': False, 'error': 'Aktuelles Passwort ist falsch'}), 400
    if len(new) < 12:
        return jsonify({'ok': False, 'error': 'Das neue Passwort muss mindestens 12 Zeichen haben'}), 400
    set_admin_password(new)
    session.clear()
    return jsonify({'ok': True, 'message': 'Passwort geändert. Bitte erneut anmelden.'})

@app.route('/')
def index(): return redirect('/public')
@app.route('/admin')
@require_admin
def admin_page(): return send_from_directory(app.static_folder, 'index.html')
@app.route('/public')
def public_page(): return send_from_directory(app.static_folder, 'public.html')
@app.route('/map/current.png')
def current_map():
    if str(read_network_settings().get('public_show_park_views', 'true')).lower() != 'true':
        return send_from_directory(app.static_folder, 'park-demo.svg', max_age=0)
    path = os.path.join(SCREENSHOT_DIR, 'server-map.png')
    if os.path.exists(path): return send_from_directory(SCREENSHOT_DIR, 'server-map.png', max_age=0)
    return send_from_directory(app.static_folder, 'park-demo.svg')

@app.route('/map/<int:rotation>.png')
def map_rotation(rotation):
    if rotation not in range(4): return ('Not Found', 404)
    if str(read_network_settings().get('public_show_park_views', 'true')).lower() != 'true':
        return send_from_directory(app.static_folder, 'park-demo.svg', max_age=0)
    filename = f'server-map-{rotation}.png'
    if os.path.exists(os.path.join(SCREENSHOT_DIR, filename)):
        return send_from_directory(SCREENSHOT_DIR, filename, max_age=0)
    return current_map()

@app.route('/downloads/current')
@require_admin
def current_park():
    filename = get_active_save()
    if filename and os.path.exists(os.path.join(SAVE_DIR, filename)):
        return send_from_directory(SAVE_DIR, filename, as_attachment=True)
    return ('Noch kein aktiver Spielstand vorhanden.', 404)

@app.get('/api/saves')
@require_admin
def api_saves(): return jsonify({'active':get_active_save(),'saves':list_saves()})

@app.post('/api/saves/upload')
@require_admin
def api_save_upload():
    f=request.files.get('file')
    if not f or not f.filename: return jsonify({'ok':False,'error':'Keine Datei ausgewählt'}),400
    name=safe_save_name(f.filename)
    if not allowed_save(name): return jsonify({'ok':False,'error':'Nur .sv6 und .park sind erlaubt'}),400
    os.makedirs(SAVE_DIR,exist_ok=True)
    f.save(os.path.join(SAVE_DIR,name))
    if not read_active_save_marker(): set_active_save(name)
    return jsonify({'ok':True,'name':name,'active':get_active_save()})

@app.post('/api/saves/activate')
@require_admin
def api_save_activate():
    try:
        name=set_active_save((request.get_json(force=True) or {}).get('name',''))
        # The game container command should read ACTIVE_SAVE_FILE on start. Restart when live.
        if not MOCK and CONTROL_MODE=='docker':
            docker_container().restart(timeout=20)
        elif MOCK:
            MOCK_STATE['server']['park']=name
        return jsonify({'ok':True,'active':name,'restarted':not MOCK})
    except Exception as e: return jsonify({'ok':False,'error':str(e)}),400

@app.delete('/api/saves/<path:name>')
@require_admin
def api_save_delete(name):
    name=safe_save_name(name)
    if name==get_active_save(): return jsonify({'ok':False,'error':'Aktiver Spielstand kann nicht gelöscht werden'}),400
    path=os.path.join(SAVE_DIR,name)
    if not allowed_save(name) or not os.path.isfile(path): return jsonify({'ok':False,'error':'Nicht gefunden'}),404
    os.remove(path); return jsonify({'ok':True})


@app.get('/api/rct2-data')
@require_admin
def api_rct2_data_status():
    return jsonify(rct2_data_status())

@app.post('/api/rct2-data/upload')
@require_admin
def api_rct2_data_upload():
    f=request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok':False,'error':'Keine ZIP-Datei ausgewählt'}),400
    if pathlib.Path(f.filename).suffix.lower() != '.zip':
        return jsonify({'ok':False,'error':'Bitte die RCT2-Originaldaten als ZIP hochladen'}),400
    try:
        status=install_rct2_zip(f)
        return jsonify({'ok':True,'status':status})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}),400

@app.delete('/api/rct2-data')
@require_admin
def api_rct2_data_delete():
    try:
        with tempfile.TemporaryDirectory(prefix='empty-rct2-') as empty_dir:
            replace_directory_contents_mount_safe(empty_dir, RCT2_DATA_DIR)
        return jsonify({'ok':True,'status':rct2_data_status()})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}),500

@app.get('/branding/logo')
def branding_logo():
    for extension in ('.png', '.jpg', '.jpeg', '.webp'):
        filename = f'logo{extension}'
        if os.path.isfile(os.path.join(BRANDING_DIR, filename)):
            return send_from_directory(BRANDING_DIR, filename, max_age=0)
    return send_from_directory(app.static_folder, 'openrct2-server-logo.png', max_age=0)

@app.post('/api/branding/logo')
@require_admin
def upload_branding_logo():
    image = request.files.get('file')
    extension = pathlib.Path(image.filename).suffix.lower() if image and image.filename else ''
    if extension not in ('.png', '.jpg', '.jpeg', '.webp'):
        return jsonify({'ok': False, 'error': 'Bitte PNG, JPG oder WebP auswählen'}), 400
    os.makedirs(BRANDING_DIR, exist_ok=True)
    for entry in pathlib.Path(BRANDING_DIR).glob('logo.*'):
        entry.unlink()
    image.save(os.path.join(BRANDING_DIR, f'logo{extension}'))
    return jsonify({'ok': True, 'logoUrl': branding_logo_url()})

@app.get('/api/preflight')
@require_admin
def api_preflight(): return jsonify(server_preflight())

@app.get('/api/backups')
@require_admin
def api_backups():
    return jsonify({'ok': True, 'backups': list_backups()})

@app.get('/api/backups/<path:name>/download')
@require_admin
def api_backup_download(name):
    backup_path = backup_file(name)
    if backup_path is None:
        return jsonify({'ok': False, 'error': 'Backup nicht gefunden'}), 404
    return send_from_directory(BACKUP_DIR, backup_path.name, as_attachment=True)

@app.post('/api/backups/<path:name>/restore')
@require_admin
def api_backup_restore(name):
    try:
        return jsonify({'ok': True, **restore_backup(name)})
    except Exception as error:
        return jsonify({'ok': False, 'error': str(error)}), 400

@app.get('/api/openrct2/versions')
@require_admin
def api_openrct2_versions():
    try:
        return jsonify({'ok': True, 'current': selected_game_image(), 'versions': available_game_versions()})
    except Exception as error:
        return jsonify({'ok': False, 'error': str(error)}), 503

@app.post('/api/openrct2/update')
@require_admin
def api_openrct2_update():
    payload = request.get_json(force=True) or {}
    if payload.get('confirm') is not True:
        return jsonify({'ok': False, 'error': 'Update muss bestätigt werden'}), 400
    try:
        return jsonify({'ok': True, **update_game_image(payload.get('version'))})
    except (ValueError, RuntimeError) as error:
        return jsonify({'ok': False, 'error': str(error)}), 400

@app.post('/api/maps/refresh')
@require_admin
def api_maps_refresh():
    try:
        return jsonify({'ok': True, 'images': capture_map_views()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 503

@app.get('/api/status')
def api_status():
    try: return jsonify(state())
    except Exception as e: return jsonify({'error': str(e), 'mock': False, 'server': {'online':False,'state':runtime_state()}}), 503

@app.get('/api/public-status')
def api_public_status():
    try:
        out = state()
        # Public switches limit the response as well as the visible page.
        out.pop('groups', None)
        out.pop('defaultGroup', None)
        out.pop('parkControls', None)
        if not out.get('publicShowPlayers'):
            out['players'] = []
        if not out.get('publicShowParkStats'):
            out.pop('parkStats', None)
        if not out.get('publicShowAnnouncements'):
            out.pop('announcements', None)
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': str(e), 'mock': False, 'server': {'online':False,'state':runtime_state()}}), 503

@app.get('/api/events')
def api_events():
    @stream_with_context
    def stream():
        while True:
            try:
                payload = state()
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as error:
                yield f"data: {json.dumps({'ok': False, 'error': str(error)})}\n\n"
            time.sleep(2)
    return Response(stream(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
@app.get('/api/permissions')
@require_admin
def api_permissions(): return jsonify(PERMISSIONS)
@app.get('/api/server/settings')
@require_admin
def get_settings(): return jsonify(read_network_settings())
@app.post('/api/server/settings')
@require_admin
def set_settings():
    payload = request.get_json(force=True) or {}
    game_settings = {'server_name', 'server_description', 'server_greeting', 'maxplayers', 'advertise', 'default_password', 'ui_language'}
    was_running = False
    try:
        was_running = bool(set(payload) & game_settings) and not MOCK and CONTROL_MODE == 'docker' and runtime_state() == 'running'
        if was_running:
            docker_container().stop(timeout=20)
        settings = write_network_settings(payload)
        if was_running:
            docker_container().start()
        return jsonify({'ok': True, 'settings': settings, 'restarted': was_running})
    except Exception as e:
        if was_running and runtime_state() != 'running':
            try:
                docker_container().start()
            except Exception:
                pass
        return jsonify({'ok':False,'error':str(e)}),400

@app.get('/api/setup')
@require_admin
def get_setup():
    return jsonify({'ok': True, **setup_status()})

@app.post('/api/setup/complete')
@require_admin
def finish_setup():
    try:
        return jsonify({'ok': True, 'settings': complete_setup(request.get_json(force=True) or {}), 'setup': setup_status()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@app.post('/api/server/control')
@require_admin
def server_control():
    action = (request.get_json(silent=True) or {}).get('action', '').strip().lower()
    if action not in ('start', 'stop', 'restart'):
        return jsonify({'ok': False, 'error': 'Ungültige Aktion'}), 400

    if action in ('start', 'restart'):
        pf = server_preflight()
        if not pf.get('ready'):
            return jsonify({
                'ok': False,
                'error': 'Serverstart gesperrt: ' + '; '.join(pf.get('reasons') or ['Preflight nicht erfüllt']),
                'preflight': pf
            }), 409

    if MOCK:
        MOCK_STATE['server']['state'] = 'running' if action in ('start', 'restart') else 'stopped'
        MOCK_STATE['server']['online'] = action in ('start', 'restart')
        return jsonify({'ok': True, 'state': MOCK_STATE['server']['state'], 'mock': True})

    if CONTROL_MODE != 'docker':
        return jsonify({'ok': False, 'error': 'Docker-Steuerung deaktiviert'}), 403
    if docker is None:
        return jsonify({'ok': False, 'error': 'Docker SDK im Admin-Container nicht verfügbar'}), 503

    try:
        client = docker.from_env()
        c = client.containers.get(GAME_CONTAINER)
        c.reload()

        if action == 'start':
            if c.status != 'running':
                c.start()
        elif action == 'stop':
            if c.status == 'running':
                c.stop(timeout=20)
        else:
            if c.status == 'running':
                c.restart(timeout=20)
            else:
                c.start()

        time.sleep(1.0)
        c.reload()
        return jsonify({'ok': True, 'state': c.status})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Docker-Fehler: {e}'}), 503

@app.get('/api/server/logs')
@require_admin
def server_logs():
    if MOCK:
        return jsonify({'ok': True, 'logs': 'Mock-Modus: keine Containerlogs verfügbar.'})
    if CONTROL_MODE != 'docker':
        return jsonify({'ok': False, 'error': 'Docker-Steuerung deaktiviert'}), 403
    try:
        logs = docker_container().logs(tail=200, timestamps=True).decode('utf-8', errors='replace')
        return jsonify({'ok': True, 'logs': logs})
    except Exception as error:
        return jsonify({'ok': False, 'error': str(error)}), 503

@app.post('/api/action')
@require_admin
def api_action():
    payload = request.get_json(force=True) or {}; cmd = payload.get('cmd')
    if cmd == 'send_message' and payload.get('confirm') is not True:
        return jsonify({'ok': False, 'error': 'Aktion muss bestätigt werden'}), 400
    if cmd == 'send_message' and (not isinstance(payload.get('message'), str) or not payload['message'].strip() or len(payload['message']) > 240):
        return jsonify({'ok': False, 'error': 'Nachricht muss 1 bis 240 Zeichen enthalten'}), 400
    if MOCK:
        if cmd == 'set_player_group':
            p = next((x for x in MOCK_STATE['players'] if x['id'] == int(payload['playerId'])), None)
            if p: p['group'] = int(payload['groupId'])
        elif cmd == 'kick_player': MOCK_STATE['players'] = [x for x in MOCK_STATE['players'] if x['id'] != int(payload['playerId'])]
        elif cmd == 'set_default_group': MOCK_STATE['defaultGroup'] = int(payload['groupId'])
        elif cmd == 'rename_group':
            g = next((x for x in MOCK_STATE['groups'] if x['id'] == int(payload['groupId'])), None)
            if g: g['name'] = str(payload['name'])[:64]
        elif cmd == 'set_group_permissions':
            g = next((x for x in MOCK_STATE['groups'] if x['id'] == int(payload['groupId'])), None)
            if g: g['permissions'] = [x for x in payload.get('permissions',[]) if x in PERMISSIONS]
        elif cmd == 'add_group':
            new_id = max([g['id'] for g in MOCK_STATE['groups']] + [0]) + 1
            MOCK_STATE['groups'].append({'id': new_id, 'name': payload.get('name','Neue Rolle'), 'permissions':['chat']})
        elif cmd == 'remove_group':
            gid = int(payload['groupId'])
            if gid == 0: return jsonify({'ok':False,'error':'Admin-Gruppe kann im Prototyp nicht gelöscht werden'}), 400
            MOCK_STATE['groups'] = [g for g in MOCK_STATE['groups'] if g['id'] != gid]
            for p in MOCK_STATE['players']:
                if p['group'] == gid: p['group'] = MOCK_STATE['defaultGroup']
        elif cmd == 'send_message': pass
        else: return jsonify({'ok':False,'error':'unknown command'}),400
        return jsonify({'ok': True, 'mock': True})
    try: return jsonify(bridge_call(payload))
    except Exception as e: return jsonify({'ok':False,'error':str(e)}),503




@app.get('/api/dashboard')
@require_admin
def api_dashboard():
    pf = server_preflight()
    return jsonify({
        'ok': True,
        'preflight': pf,
        'runtime': runtime_state(),
        'saves': list_saves(),
        'active_save': get_active_save(),
        'settings': read_network_settings(),
        'setup': setup_status(),
        'backups': list_backups(),
        'image': selected_game_image(),
    })


@app.errorhandler(413)
def handle_413(e):
    return jsonify({"ok": False, "error": "Datei ist zu groß für den Upload."}), 413

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "API-Endpunkt nicht gefunden."}), 404
    return ("Not Found", 404)

@app.errorhandler(Exception)
def handle_api_exception(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500
    raise e


if __name__ == '__main__': app.run(host='0.0.0.0', port=8088)
