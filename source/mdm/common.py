import json
import os
from pathlib import Path
import re
import urllib.parse
from .platform_support import WINDOWS, filelocks as fcntl, sync_directory

BASE = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get('MDM_STATE_DIR', str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Mezba Download Manager' / 'State') if WINDOWS else str(Path.home() / '.local/state/mdm-windows-dev')))
SOCKET = STATE / 'service.sock'
DEFAULTS = {'folder': str(Path.home() / 'Downloads/MDM'), 'concurrent': 2,
            'connections': 4, 'speed_kib': 0, 'cookies_browser': '', 'retries': 8}
BROWSERS = ('', 'firefox', 'chrome', 'chromium', 'brave', 'edge', 'vivaldi')

def init_state():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)

def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    with open(temp, 'w', encoding='utf-8') as f:
        os.chmod(temp, 0o600)
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    sync_directory(path.parent)

def url_checked(value):
    if not isinstance(value, str) or len(value) > 16384 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid URL')
    p = urllib.parse.urlsplit(value.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Use an HTTP or HTTPS URL without embedded credentials.')
    return value.strip()

def safe_name(value):
    value = re.sub(r'[\x00-\x1f\x7f/\\<>:"|?*]', '_', str(value)).strip(' .')
    value = (value or 'download')[:160]
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:value='_'+value
    return value

def human(value):
    value = float(value or 0)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}'
        value /= 1024

def update_in_progress():
    init_state()
    if (STATE/'installing.json').exists():return True
    with open(STATE / 'update.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True
