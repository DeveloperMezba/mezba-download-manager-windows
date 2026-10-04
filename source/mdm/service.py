from .platform_support import filelocks as fcntl, hidden_process, worker_python, spawn_background
import json
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from .common import BASE, STATE, SOCKET, DEFAULTS, BROWSERS, atomic_json, init_state, safe_name, url_checked
from .http_engine import Transfer, Paused
from . import media, __version__
from .common import update_in_progress

MAX_MESSAGE = 256 * 1024

def request(message, autostart=True, timeout=125):
    init_state()
    if update_in_progress():
        raise RuntimeError('MDM is updating. Downloads are saved; please wait a moment.')
    try:
        return _request(message, timeout)
    except (FileNotFoundError, ConnectionRefusedError):
        if not autostart:
            raise
        with open(STATE / 'service.log', 'ab') as log:
            spawn_background([worker_python(), '-X', 'utf8', str(BASE / 'mdm.py'), '--daemon'],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                return _request(message, timeout)
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
        raise RuntimeError(f'MDM service did not start. Open MDM from the Start menu, then retry. Log: {STATE / "service.log"}')

def _request(message, timeout):
    data = json.dumps(message).encode() + b'\n'
    if len(data) > MAX_MESSAGE:
        raise ValueError('Request too large')
    from .ipc import exchange
    return exchange(message, timeout)

class Manager:
    def __init__(self):
        init_state()
        self.lock = threading.RLock()
        self.closing = threading.Event()
        self.active = {}
        self.updating = False
        self.analyses = 0
        self.tool_update = {'busy': False, 'message': '', 'progress': 0, 'error': ''}
        self.db = sqlite3.connect(STATE / 'queue.sqlite', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.tasks = {i: json.loads(data) for i, data in self.db.execute('SELECT id,data FROM tasks')}
        self.settings = dict(DEFAULTS)
        if (STATE / 'settings.json').exists():
            self.settings.update(json.loads((STATE / 'settings.json').read_text()))
        for task in self.tasks.values():
            if task['status'] in ('downloading', 'pausing', 'verifying'):
                task.update(status='paused', error='Recovered after interruption. Press Resume to continue.')
                self.save(task)
        # A power loss during a tool switch keeps recoverable jobs paused.
        (STATE / 'tools-resume.json').unlink(missing_ok=True)
        self.scheduler = threading.Thread(target=self.schedule, daemon=True)
        self.scheduler.start()

    def save(self, task):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)', (task['id'], json.dumps(task)))
            self.db.commit()

    def add(self, data):
        url = url_checked(data.get('url', ''))
        kind = data.get('kind', 'file')
        host = urllib.parse.urlsplit(url).hostname
        if kind == 'file' and host in ('drive.google.com', 'docs.google.com'):
            kind = 'drive'
        if kind not in ('file', 'media', 'drive'):
            raise ValueError('Unknown download type')
        if kind == 'drive' and ('/folders/' in urllib.parse.urlsplit(url).path or '/document/' in urllib.parse.urlsplit(url).path or '/spreadsheets/' in urllib.parse.urlsplit(url).path or '/presentation/' in urllib.parse.urlsplit(url).path):
            raise ValueError('Use a public single-file Drive link; folders and Docs export are not supported.')
        if kind == 'drive' and host not in ('drive.google.com', 'docs.google.com'):
            raise ValueError('Use a Google Drive sharing URL')
        quality = data.get('quality', 'best')
        if kind == 'media':
            media.split_choice(quality)
        digest = str(data.get('sha256', '')).lower().strip()
        if digest and (kind != 'file' or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('SHA-256 must be 64 hexadecimal characters and is available for direct files.')
        title = str(data.get('title', '')).strip()[:300]
        filename = safe_name(data.get('filename') or urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]) or 'download.bin')
        if kind == 'drive' and not data.get('filename'):
            filename = 'Google-Drive-file'
        task_id = uuid.uuid4().hex[:12]
        folder = Path(self.settings['folder']).expanduser().resolve() / (safe_name(title or filename)[:60] + '-' + task_id)
        delay = max(0, min(int(data.get('delay_minutes', 0)), 525600))
        task = {'id': task_id, 'url': url, 'kind': kind, 'quality': quality,
                'title': title or filename, 'filename': filename, 'folder': str(folder),
                'status': 'queued', 'done': 0, 'total': None, 'speed': 0, 'error': '',
                'created': time.time(), 'start_at': time.time() + delay * 60,
                'sha256': digest, 'output': ''}
        with self.lock:
            if len(self.tasks) >= 2000:
                raise ValueError('History is full. Remove some finished tasks.')
            self.tasks[task_id] = task
            self.save(task)
        return task.copy()

    def dispatch(self, message):
        action = message.get('action')
        if action == 'ping':
            return {'version': __version__}
        if action == 'tools_status':
            with self.lock:
                return self.tool_update.copy()
        if action == 'tools_versions':
            from .tool_updater import inventory
            return inventory()
        if action == 'tools_update':
            with self.lock:
                if self.tool_update['busy'] or self.updating or update_in_progress():
                    raise ValueError('An update is already running.')
                self.tool_update = {'busy': True, 'message': 'Checking download tools…', 'progress': 0, 'error': ''}
                threading.Thread(target=self.update_tools, daemon=True).start()
                return self.tool_update.copy()
        if (self.updating or update_in_progress()) and action in ('add','analyze','resume','settings','replace_url','remove'):
            raise ValueError('MDM is updating. Please wait before starting or changing downloads.')
        if action == 'analyze':
            with self.lock:
                if self.updating:
                    raise ValueError('MDM is updating. Please wait.')
                self.analyses += 1
            try:
                return media.analyze(url_checked(message.get('url', '')), self.settings.copy())
            finally:
                with self.lock:
                    self.analyses -= 1
        if action == 'add':
            return self.add(message)
        with self.lock:
            if action == 'list':
                return {'tasks': [t.copy() for t in sorted(self.tasks.values(), key=lambda t: t['created'], reverse=True)],
                        'settings': self.settings.copy()}
            if action == 'settings':
                data = message.get('settings', {})
                updated = dict(self.settings)
                if 'folder' in data:
                    folder = Path(data['folder']).expanduser()
                    if not folder.is_absolute():
                        raise ValueError('Choose an absolute destination path.')
                    folder.mkdir(parents=True, exist_ok=True)
                    updated['folder'] = str(folder.resolve())
                for key, low, high in [('concurrent', 1, 4), ('connections', 1, 8), ('speed_kib', 0, 1000000), ('retries', 0, 30)]:
                    if key in data:
                        n = int(data[key])
                        if not low <= n <= high:
                            raise ValueError(f'{key} must be between {low} and {high}')
                        updated[key] = n
                if 'cookies_browser' in data:
                    if data['cookies_browser'] not in BROWSERS:
                        raise ValueError('Unsupported browser')
                    updated['cookies_browser'] = data['cookies_browser']
                atomic_json(STATE / 'settings.json', updated)
                self.settings = updated
                return updated
            if action == 'prepare_update':
                if self.tool_update['busy']:
                    raise ValueError('Wait for the download-tool update to finish before updating the app.')
                self.updating = True
                restore = {t['id']:t['start_at'] for t in self.tasks.values() if t['status'] in ('queued','downloading')}
                for task in self.tasks.values():
                    if task['status'] in ('queued','downloading'):
                        self.pause(task)
                return restore
            if action == 'restore_after_update':
                for task_id, start_at in message.get('restore', {}).items():
                    task = self.tasks.get(task_id)
                    if task and task['status'] == 'paused':
                        task.update(status='queued',start_at=float(start_at),error='')
                        self.save(task)
                self.updating = False
                return True
            if action == 'update_ready':
                return not self.active and not self.analyses
            if action == 'pause_all':
                for t in self.tasks.values():
                    if t['status'] in ('queued', 'downloading'):
                        self.pause(t)
                return True
            if action == 'shutdown':
                if self.tool_update['busy']:
                    raise ValueError('A tool update is running. Wait for it to finish before stopping MDM.')
                self.closing.set()
                for t in self.tasks.values():
                    if t['id'] in self.active:
                        self.pause(t)
                return True
            task = self.tasks.get(message.get('id'))
            if not task:
                raise ValueError('Download not found')
            if action == 'get':
                return task.copy()
            if action == 'pause':
                self.pause(task)
            elif action == 'resume':
                if task['id'] in self.active:
                    raise ValueError('Wait until the download has paused.')
                if task['status'] == 'complete':
                    return task.copy()
                task.update(status='queued', error='', start_at=time.time())
            elif action == 'replace_url':
                if task['id'] in self.active or task['status'] == 'complete':
                    raise ValueError('Pause the download before replacing its link.')
                new_url = url_checked(message.get('url', ''))
                if task['kind'] != 'file':
                    raise ValueError('For video or Drive, resume reopens the original page. Use a new task for a different page.')
                task.update(url=new_url, status='paused', error='Link changed. Resume will verify file identity before writing.')
            elif action == 'remove':
                if task['id'] in self.active:
                    raise ValueError('Pause before removing the history entry.')
                del self.tasks[task['id']]
                self.db.execute('DELETE FROM tasks WHERE id=?', (task['id'],))
                self.db.commit()
                return True
            else:
                raise ValueError('Unknown action')
            self.save(task)
            return task.copy()

    def update_tools(self):
        from . import tool_updater
        restore = {}
        maintenance = False
        def progress(message, value):
            with self.lock:
                self.tool_update.update(message=message, progress=value)
        try:
            # Downloads can continue while the replacement bundle is staged.
            bundle = tool_updater.stage(progress)
            if bundle is None:
                progress('Your download tools are already up to date.', 1)
                return
            with self.lock:
                self.updating = maintenance = True
                restore = {t['id']: t['start_at'] for t in self.tasks.values() if t['status'] in ('queued', 'downloading')}
                atomic_json(STATE / 'tools-resume.json', restore)
                for task_id in restore:
                    self.pause(self.tasks[task_id])
            progress('Saving active downloads before switching tools…', .93)
            deadline = time.monotonic() + 150
            while True:
                with self.lock:
                    ready = not self.active and not self.analyses
                if ready:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('Downloads are still stopping. The existing tools were kept. Retry after pausing them.')
                time.sleep(.2)
            tool_updater.activate_bundle(bundle)
            progress('Download tools updated. Your app version stays ' + __version__ + '.', 1)
        except Exception as error:
            with self.lock:
                self.tool_update.update(error=str(error), message='Tool update did not finish. See the details below.')
        finally:
            with self.lock:
                if maintenance:
                    for task_id, start_at in restore.items():
                        task = self.tasks.get(task_id)
                        if task and task['status'] == 'paused':
                            task.update(status='queued', start_at=start_at, error='')
                            self.save(task)
                    self.updating = False
                    (STATE / 'tools-resume.json').unlink(missing_ok=True)
                self.tool_update['busy'] = False

    def pause(self, task):
        if task['id'] in self.active:
            task['status'] = 'pausing'
            self.active[task['id']].set()
        elif task['status'] != 'complete':
            task['status'] = 'paused'
        self.save(task)

    def schedule(self):
        while not self.closing.wait(0.3):
            with self.lock:
                if self.updating or update_in_progress():
                    continue
                for task in sorted(self.tasks.values(), key=lambda t: t['created']):
                    if len(self.active) >= self.settings['concurrent']:
                        break
                    if task['status'] == 'queued' and task['start_at'] <= time.time():
                        stop = threading.Event()
                        self.active[task['id']] = stop
                        task.update(status='downloading', error='', speed=0)
                        self.save(task)
                        threading.Thread(target=self.run, args=(task, stop, self.settings.copy()), daemon=True).start()

    def run(self, task, stop, settings):
        last_saved = 0
        def progress(done, total, speed):
            nonlocal last_saved
            with self.lock:
                task.update(done=done, total=total, speed=speed)
                if time.monotonic() - last_saved > 1:
                    self.save(task)
                    last_saved = time.monotonic()
        def item_progress(index, count, title):
            with self.lock:
                task.update(playlist_index=index, playlist_count=count, item_title=title, done=0, total=None, speed=0)
                self.save(task)
        try:
            if task['kind'] == 'file':
                transfer = Transfer(task['url'], task['folder'], task['filename'], stop, progress,
                                    settings['connections'], settings['speed_kib'], settings['retries'], task['sha256'])
                output = transfer.run()
            else:
                output = media.run_external(task, settings, stop, progress, item_progress)
            with self.lock:
                task.update(status='complete', speed=0, output=output, error='')
        except Paused:
            with self.lock:
                task.update(status='paused', speed=0, error='')
        except Exception as e:
            with self.lock:
                task.update(status='paused' if stop.is_set() else 'error', speed=0, error=str(e)[:3000])
        finally:
            with self.lock:
                self.save(task)
                self.active.pop(task['id'], None)

def serve():
    from .ipc import run_server
    init_state()
    with open(STATE / 'service.lock', 'a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        manager=Manager()
        run_server(manager)
