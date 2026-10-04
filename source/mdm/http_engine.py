from .platform_support import WINDOWS, pwrite, promote, sync_directory, set_sparse
"""Bounded-memory HTTP downloads with validated ranges and durable checkpoints."""
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from .common import atomic_json, url_checked

BLOCK = 256 * 1024

class DownloadError(Exception):
    pass

class Paused(DownloadError):
    pass

class HTTPOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url_checked(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def open_url(url, headers):
    req = urllib.request.Request(url_checked(url), headers={
        'User-Agent': 'MezbaDownloadManager/0.1', 'Accept-Encoding': 'identity', **headers})
    return urllib.request.build_opener(HTTPOnlyRedirect()).open(req, timeout=20)

def validator(headers):
    etag = headers.get('ETag', '')
    if etag and not etag.startswith('W/'):
        return ('etag', etag)
    modified = headers.get('Last-Modified', '')
    return ('modified', modified) if modified else ('', '')

def parse_range(value):
    m = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', value or '')
    if not m:
        raise DownloadError('Server returned an invalid byte range.')
    return tuple(map(int, m.groups()))

def probe(url):
    try:
        with open_url(url, {'Range': 'bytes=0-0'}) as response:
            encoding = response.headers.get('Content-Encoding', 'identity')
            if encoding != 'identity':
                raise DownloadError('Server ignored identity encoding; safe resume is unavailable.')
            ranges = response.status == 206
            if ranges:
                start, end, size = parse_range(response.headers.get('Content-Range'))
                if (start, end) != (0, 0):
                    raise DownloadError('Server returned an unexpected probe range.')
            else:
                if response.status != 200:
                    raise DownloadError(f'Unexpected HTTP status {response.status}')
                length = response.headers.get('Content-Length')
                size = int(length) if length is not None else None
            key, tag = validator(response.headers)
            return {'size': size, 'ranges': ranges, 'validator_key': key, 'validator': tag,
                    'type': response.headers.get('Content-Type', '')}
    except urllib.error.HTTPError as e:
        if e.code == 416 and e.headers.get('Content-Range') == 'bytes */0':
            return {'size': 0, 'ranges': False, 'validator_key': '', 'validator': '', 'type': ''}
        raise

class Transfer:
    def __init__(self, url, folder, filename, stop, progress, connections=4,
                 speed_kib=0, retries=8, checksum=''):
        self.url = url_checked(url)
        self.folder = Path(folder)
        self.final = self.folder / filename
        self.part = self.folder / (filename + '.mdm-part')
        self.journal = self.folder / (filename + '.mdm-state')
        self.stop = stop
        self.progress = progress
        self.connections = max(1, min(int(connections), 8))
        self.speed = max(0, int(speed_kib)) * 1024
        self.retries = max(0, min(int(retries), 30))
        self.checksum = checksum
        self.lock = threading.RLock()
        self.rate_lock = threading.Lock()
        self.abort = threading.Event()
        self.rate_time = time.monotonic()
        self.last_save = 0
        self.last_report = time.monotonic()
        self.last_bytes = 0
        self.fd = None
        self.state = None

    def interrupted(self):
        return self.stop.is_set() or self.abort.is_set()

    def backoff(self, attempt):
        until = time.monotonic() + min(2 ** attempt, 30)
        while time.monotonic() < until:
            if self.interrupted():
                raise Paused('Paused; saved partial data is retained.')
            time.sleep(0.1)

    def throttle(self, length):
        if not self.speed:
            return
        with self.rate_lock:
            now = time.monotonic()
            self.rate_time = max(now, self.rate_time) + length / self.speed
            target = self.rate_time
        while time.monotonic() < target:
            if self.interrupted():
                raise Paused('Paused')
            time.sleep(min(0.1, target - time.monotonic()))

    def checkpoint(self, force=False):
        with self.lock:
            now = time.monotonic()
            total = sum(s['done'] for s in self.state['segments'])
            if force or now - self.last_save >= 1:
                # Writes finish before counters advance. Flushing before metadata makes a
                # crash lose at most the uncheckpointed interval, never invent progress.
                os.fsync(self.fd)
                atomic_json(self.journal, self.state)
                self.last_save = now
            if force or now - self.last_report >= 0.4:
                speed = max(0, total - self.last_bytes) / max(0.001, now - self.last_report)
                self.progress(total, self.state['remote']['size'], speed)
                self.last_bytes, self.last_report = total, now

    def run(self):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.final.exists():
            # Only a completed journal proves this is our already-renamed file.
            if self.journal.exists():
                saved = json.loads(self.journal.read_text())
                if saved.get('complete') and self.final.stat().st_size == saved['remote']['size']:
                    self.verify(self.final)
                    self.progress(self.final.stat().st_size, self.final.stat().st_size, 0)
                    return str(self.final)
            raise DownloadError('Output already exists. MDM will not overwrite it.')
        if self.journal.exists() and self.part.exists():
            saved = json.loads(self.journal.read_text())
            # Crash after the durable completion marker but before final rename.
            if saved.get('complete') and self.part.stat().st_size == saved['remote']['size']:
                self.verify(self.part)
                promote(self.part, self.final)
                self.progress(self.final.stat().st_size, self.final.stat().st_size, 0)
                return str(self.final)
        remote = None
        for attempt in range(self.retries + 1):
            try:
                remote = probe(self.url)
                break
            except urllib.error.HTTPError as e:
                if e.code not in (408, 429, 500, 502, 503, 504) or attempt == self.retries:
                    raise DownloadError(f'HTTP {e.code}. Check access or refresh the URL.') from e
                self.backoff(attempt)
            except (OSError, http.client.HTTPException) as e:
                if attempt == self.retries:
                    raise DownloadError(str(e)) from e
                self.backoff(attempt)
        if self.interrupted():
            raise Paused('Paused')
        if self.journal.exists():
            self.state = json.loads(self.journal.read_text())
            old = self.state['remote']
            if not self.part.exists():
                raise DownloadError('Partial file is missing. Add a new download.')
            if any(s['done'] and self.part.stat().st_size < s['start'] + s['done'] for s in self.state['segments']):
                raise DownloadError('Partial file was truncated. Add a new download.')
            done = sum(s['done'] for s in self.state['segments'])
            if done:
                if not old['ranges'] or not remote['ranges'] or not old['validator']:
                    raise DownloadError('Server does not support verifiable resume. Add a new download to restart safely.')
                if any(old[k] != remote[k] for k in ('size', 'validator_key', 'validator')):
                    raise DownloadError('The remote file changed. Partial data was kept; add a new download.')
            elif not old['ranges']:
                self.state = None
        if self.state is None:
            size = remote['size']
            if remote['ranges'] and remote['validator'] and size and size >= 4 * 1024 * 1024:
                count = self.connections
            else:
                count = 1
            segments = []
            for i in range(count):
                start = size * i // count if size is not None else 0
                end = size * (i + 1) // count if size is not None else None
                segments.append({'start': start, 'end': end, 'done': 0})
            self.state = {'version': 1, 'remote': remote, 'segments': segments, 'complete': False}
        remaining = (remote['size'] or 0) - sum(s['done'] for s in self.state['segments'])
        if remaining and shutil.disk_usage(self.folder).free < remaining + 8 * 1024 * 1024:
            raise DownloadError('Not enough free disk space for the remaining download.')
        self.fd = os.open(self.part, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
        set_sparse(self.fd)
        try:
            self.last_bytes = sum(s['done'] for s in self.state['segments'])
            self.checkpoint(True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.state['segments'])) as pool:
                futures = [pool.submit(self.segment, s) for s in self.state['segments']]
                errors = []
                for f in concurrent.futures.as_completed(futures):
                    try:
                        f.result()
                    except Exception as e:
                        errors.append(e)
                        self.abort.set()
                if errors:
                    raise next((e for e in errors if not isinstance(e, Paused)), errors[0])
            if self.interrupted():
                raise Paused('Paused')
            self.checkpoint(True)
            size = sum(s['done'] for s in self.state['segments'])
            os.ftruncate(self.fd, size)
            os.fsync(self.fd)
            self.verify(self.part)
            self.state['remote']['size'] = size
            self.state['complete'] = True
            atomic_json(self.journal, self.state)
            # Exclusive final creation prevents a concurrent user file being overwritten.
            if WINDOWS:
                os.close(self.fd)
                self.fd = None
            promote(self.part, self.final)
            sync_directory(self.folder)
            self.progress(size, size, 0)
            return str(self.final)
        finally:
            if self.fd is not None:
                self.checkpoint(True)
                os.close(self.fd)

    def verify(self, path):
        if not self.checksum:
            return
        digest = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                if self.stop.is_set():
                    raise Paused('Paused during verification')
                data = f.read(1024 * 1024)
                if not data:
                    break
                digest.update(data)
        if digest.hexdigest() != self.checksum:
            raise DownloadError('SHA-256 mismatch. Partial data kept; do not use this file.')

    def segment(self, segment):
        remote = self.state['remote']
        attempts = 0
        while segment['end'] is None or segment['start'] + segment['done'] < segment['end']:
            if self.interrupted():
                raise Paused('Paused')
            start = segment['start'] + segment['done']
            headers = {}
            if remote['ranges']:
                headers['Range'] = f"bytes={start}-{segment['end'] - 1}"
                if remote['validator']:
                    headers['If-Range'] = remote['validator']
            elif segment['done']:
                raise DownloadError('Connection broke on a server without ranges. Add a new download to restart.')
            try:
                with open_url(self.url, headers) as response:
                    if remote['ranges']:
                        if response.status != 206:
                            raise DownloadError('Server refused resume or the file changed. Partial data kept.')
                        first, last, size = parse_range(response.headers.get('Content-Range'))
                        if (first, last, size) != (start, segment['end'] - 1, remote['size']):
                            raise DownloadError('Server sent the wrong range. Stopped to prevent corruption.')
                    elif response.status != 200:
                        raise DownloadError('Unexpected response for a non-range download.')
                    if response.headers.get('Content-Encoding', 'identity') != 'identity':
                        raise DownloadError('Unexpected compressed response.')
                    if remote['validator']:
                        key, val = validator(response.headers)
                        if (key, val) != (remote['validator_key'], remote['validator']):
                            raise DownloadError('File identity changed during transfer.')
                    while True:
                        if self.interrupted():
                            raise Paused('Paused')
                        remaining = None if segment['end'] is None else segment['end'] - segment['start'] - segment['done']
                        if remaining == 0:
                            return
                        data = response.read(min(BLOCK, remaining) if remaining is not None else BLOCK)
                        if not data:
                            if remaining is not None and remaining > 0:
                                raise ConnectionError('Connection closed before the requested range finished.')
                            return
                        self.throttle(len(data))
                        offset = segment['start'] + segment['done']
                        view = memoryview(data)
                        while view:
                            written = pwrite(self.fd, view, offset, self.lock)
                            if written <= 0:
                                raise DownloadError('Disk write failed.')
                            view, offset = view[written:], offset + written
                        with self.lock:
                            segment['done'] += len(data)
                        self.checkpoint()
            except urllib.error.HTTPError as e:
                if e.code not in (408, 429, 500, 502, 503, 504):
                    raise DownloadError(f'HTTP {e.code}. Pause and refresh the link or check access.') from e
                attempts += 1
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
                attempts += 1
            # A request without a validator cannot safely join old and new content.
            if segment['done'] and not remote['validator']:
                raise DownloadError('Connection lost; server supplied no file validator. Restart as a new download.')
            if attempts > self.retries:
                raise DownloadError('Retry limit reached. Partial data saved; resume when the connection returns.')
            self.backoff(attempts)
