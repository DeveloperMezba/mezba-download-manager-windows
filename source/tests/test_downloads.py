import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mdm.http_engine import Transfer, DownloadError, Paused
from mdm.common import safe_name, url_checked
from mdm.media import choices, format_args

DATA = bytes(range(256)) * (32 * 1024)  # 8 MiB, deterministic checksum
HASH = hashlib.sha256(DATA).hexdigest()

class Fixture(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    requests = []
    failed = False
    tag = '"fixture-v1"'
    lock = threading.Lock()
    def log_message(self, *_):
        pass
    def do_GET(self):
        with self.lock:
            self.requests.append((self.path, self.headers.get('Range'), self.headers.get('If-Range')))
        source = DATA if self.path != '/empty' else b''
        start, end = 0, len(source) - 1
        ranged = bool(self.headers.get('Range')) and self.path != '/no-range'
        if ranged:
            start, end = map(int, self.headers['Range'][6:].split('-'))
            if start >= len(source):
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{len(source)}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            end = min(end, len(source) - 1)
        self.send_response(206 if ranged else 200)
        if self.path != '/no-validator':
            self.send_header('ETag', self.tag)
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Content-Type', 'application/octet-stream')
        if ranged:
            reported = start + 1 if self.path == '/bad-range' and end > 0 else start
            self.send_header('Content-Range', f'bytes {reported}-{end}/{len(source)}')
        self.end_headers()
        cut = False
        with self.lock:
            if self.path == '/disconnect' and end > 0 and not Fixture.failed:
                Fixture.failed = True
                cut = True
        send_end = min(end + 1, start + 600000) if cut else end + 1
        try:
            for pos in range(start, send_end, 32768):
                self.wfile.write(source[pos:min(pos + 32768, send_end)])
                if self.path == '/slow':
                    time.sleep(0.012)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        if cut:
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

class Downloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        Fixture.requests, Fixture.failed, Fixture.tag = [], False, '"fixture-v1"'
    def tearDown(self):
        self.temp.cleanup()
    def transfer(self, route='/file', stop=None, callback=None, **kwargs):
        return Transfer(self.base + route, self.folder, 'download.bin', stop or threading.Event(),
                        callback or (lambda *_: None), retries=1, **kwargs)
    def assert_file(self):
        self.assertEqual(hashlib.sha256((self.folder / 'download.bin').read_bytes()).hexdigest(), HASH)
    def test_segmented_hash(self):
        self.transfer(checksum=HASH).run()
        self.assert_file()
        ranges = {r for _, r, _ in Fixture.requests if r != 'bytes=0-0'}
        self.assertGreaterEqual(len(ranges), 4)
    def test_pause_resume(self):
        stop = threading.Event()
        def progress(done, total, speed):
            if done > 300000:
                stop.set()
        with self.assertRaises(Paused):
            self.transfer('/slow', stop, progress).run()
        checkpoint = json.loads((self.folder / 'download.bin.mdm-state').read_text())
        self.assertGreater(sum(s['done'] for s in checkpoint['segments']), 0)
        self.transfer('/slow').run()
        self.assert_file()
    def test_disconnect_retries_and_resumes(self):
        self.transfer('/disconnect', connections=1).run()
        self.assert_file()
        self.assertTrue(Fixture.failed)
        self.assertTrue(any(r and not r.startswith('bytes=0-') for _, r, _ in Fixture.requests))
    def test_changed_file_refused(self):
        stop = threading.Event()
        with self.assertRaises(Paused):
            self.transfer('/slow', stop, lambda done, *_: stop.set() if done > 300000 else None).run()
        Fixture.tag = '"different-file"'
        with self.assertRaisesRegex(DownloadError, 'changed'):
            self.transfer('/slow').run()
        self.assertFalse((self.folder / 'download.bin').exists())
    def test_refreshed_url_same_identity(self):
        stop = threading.Event()
        with self.assertRaises(Paused):
            self.transfer('/slow', stop, lambda done, *_: stop.set() if done > 300000 else None).run()
        self.transfer('/new-link').run()
        self.assert_file()
    def test_nonrange_download(self):
        self.transfer('/no-range').run()
        self.assert_file()
    def test_nonrange_resume_refused(self):
        stop = threading.Event()
        with self.assertRaises(Paused):
            self.transfer('/no-range', stop, lambda done, *_: stop.set() if done > 0 else None, speed_kib=6000).run()
        with self.assertRaisesRegex(DownloadError, 'verifiable resume'):
            self.transfer('/no-range').run()
    def test_missing_validator_resume_refused(self):
        stop = threading.Event()
        with self.assertRaises(Paused):
            self.transfer('/no-validator', stop, lambda done, *_: stop.set() if done > 0 else None, speed_kib=6000).run()
        with self.assertRaisesRegex(DownloadError, 'verifiable resume'):
            self.transfer('/no-validator').run()
    def test_wrong_range_rejected(self):
        with self.assertRaisesRegex(DownloadError, 'wrong range'):
            self.transfer('/bad-range').run()
        self.assertFalse((self.folder / 'download.bin').exists())
    def test_checksum_failure_keeps_partial(self):
        with self.assertRaisesRegex(DownloadError, 'SHA-256 mismatch'):
            self.transfer(checksum='0' * 64).run()
        self.assertFalse((self.folder / 'download.bin').exists())
        self.assertTrue((self.folder / 'download.bin.mdm-part').exists())
    def test_no_overwrite(self):
        (self.folder / 'download.bin').write_text('Do not overwrite me')
        with self.assertRaisesRegex(DownloadError, 'already exists'):
            self.transfer().run()
        self.assertEqual((self.folder / 'download.bin').read_text(), 'Do not overwrite me')
    def test_empty_file(self):
        self.transfer('/empty').run()
        self.assertEqual((self.folder / 'download.bin').stat().st_size, 0)
    def test_large_offset_no_32bit_truncation(self):
        # Sparse-file seek exercises 100 GiB offsets without downloading 100 GiB.
        path = self.folder / 'large-offset'
        offset = 100 * 1024 ** 3
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os,'O_BINARY',0), 0o600)
        try:
            from mdm.platform_support import pwrite, set_sparse
            if not set_sparse(fd):self.skipTest('Sparse-file support required for the large-offset fixture')
            pwrite(fd,b'MDM',offset,threading.Lock())
            os.lseek(fd,offset,os.SEEK_SET)
            self.assertEqual(os.read(fd,3),b'MDM')
            self.assertEqual(os.fstat(fd).st_size, offset + 3)
        finally:
            os.close(fd)
    def test_truncated_partial_refused(self):
        stop = threading.Event()
        with self.assertRaises(Paused):
            self.transfer('/slow', stop, lambda done, *_: stop.set() if done > 300000 else None).run()
        with open(self.folder / 'download.bin.mdm-part', 'r+b') as file:
            file.truncate(0)
        with self.assertRaisesRegex(DownloadError, 'truncated'):
            self.transfer('/slow').run()

    def test_completed_journal_recovers_before_rename(self):
        self.transfer('/no-range').run()
        (self.folder / 'download.bin').rename(self.folder / 'download.bin.mdm-part')
        # No request is needed: the completion marker was already made durable.
        Fixture.requests = []
        self.transfer('/no-range').run()
        self.assert_file()
        self.assertEqual(Fixture.requests, [])

    def test_format_choices(self):
        result = choices({'formats': [{'height': 2160, 'vcodec': 'av1', 'acodec': 'none'},
                          {'height': 720, 'vcodec': 'h264', 'acodec': 'aac'},
                          {'height': 1080, 'vcodec': 'h264', 'has_drm': True}]})
        ids = [c['id'] for c in result]
        self.assertEqual(ids, ['best', 'mp4:best', 'v:2160', 'mp4:v:2160', 'v:720', 'mp4:v:720', 'audio', 'mp3'])
        self.assertIn('height<=2160', format_args('v:2160')[1])
        with self.assertRaises(ValueError):
            format_args('$(touch /tmp/injected)')
    def test_input_restrictions(self):
        for url in ('file:///etc/passwd', 'javascript:alert(1)', 'https://a\n--exec=bad', 'https://user:pass@example.com'):
            with self.assertRaises(ValueError):
                url_checked(url)
        self.assertNotIn('/', safe_name('../../etc/passwd'))
        self.assertNotIn('\\', safe_name('..\\secret'))
    def test_manager_crash_recovery_without_socket(self):
        state = self.folder / 'manager-state'
        env = dict(os.environ, MDM_STATE_DIR=str(state), PYTHONPATH=str(ROOT))
        script = """
import json,sys,time
from mdm.service import Manager
m=Manager()
m.dispatch({'action':'settings','settings':{'folder':sys.argv[1],'connections':1}})
t=m.dispatch({'action':'add','url':sys.argv[2]})
while True:
 t=m.dispatch({'action':'list'})['tasks'][0]
 if t['done']>1000000:
  print('READY',flush=True)
  break
 time.sleep(.05)
while True:time.sleep(1)
"""
        process = subprocess.Popen([sys.executable,'-c',script,str(self.folder/'out'),self.base+'/slow'],
                  env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'READY')
        finally:
            process.kill();process.wait(timeout=5)
            process.stdout.close();process.stderr.close()
        restart = """
import json,time
from mdm.service import Manager
m=Manager()
t=m.dispatch({'action':'list'})['tasks'][0]
assert t['status']=='paused',t
m.dispatch({'action':'resume','id':t['id']})
deadline=time.monotonic()+15
while time.monotonic()<deadline:
 t=m.dispatch({'action':'list'})['tasks'][0]
 if t['status'] in ('complete','error'):break
 time.sleep(.05)
print(json.dumps(t))
m.closing.set()
"""
        result=subprocess.run([sys.executable,'-c',restart],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        task=json.loads(result.stdout)
        self.assertEqual(task['status'],'complete',task['error'])
        self.assertEqual(hashlib.sha256(Path(task['output']).read_bytes()).hexdigest(),HASH)

    def test_native_framing_rejects_privileged_action(self):
        msg=json.dumps({'action':'settings','settings':{'folder':'/tmp'}}).encode()
        result=subprocess.run([sys.executable,str(ROOT/'mdm.py'),'--native'],
            input=struct.pack('=I',len(msg))+msg,capture_output=True,timeout=5)
        size=struct.unpack('=I',result.stdout[:4])[0]
        self.assertEqual(size,len(result.stdout)-4)
        self.assertFalse(json.loads(result.stdout[4:])['ok'])

    def test_daemon_crash_recovery_and_native_framing(self):
        state = self.folder / 'state'
        env = dict(os.environ, MDM_STATE_DIR=str(state))
        def start():
            process = subprocess.Popen([sys.executable, str(ROOT/'mdm.py'), '--daemon'], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for _ in range(100):
                try:
                    call({'action': 'ping'})
                    return process
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(.05)
            raise AssertionError('daemon did not start')
        def call(msg):
            endpoint=json.loads((state/'endpoint.json').read_text())
            with socket.create_connection(('127.0.0.1',endpoint['port']),timeout=4) as sock:
                sock.sendall(json.dumps({'token':endpoint['token'],'message':msg}).encode()+b'\n')
                with sock.makefile('rb') as f:
                    result = json.loads(f.readline())
            if not result['ok']:
                raise RuntimeError(result['error'])
            return result['result']
        p = start()
        try:
            call({'action':'settings','settings':{'folder':str(self.folder/'output'),'connections':1}})
            task = call({'action':'add','url':self.base+'/slow'})
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                current=call({'action':'list'})['tasks'][0]
                if current['done'] > 1000000:
                    break
                time.sleep(.1)
            self.assertGreater(current['done'],1000000)
            p.kill(); p.wait(timeout=5); p.stderr.close()
            p = start()
            current = call({'action':'list'})['tasks'][0]
            self.assertEqual(current['status'], 'paused')
            call({'action':'resume','id':task['id']})
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                current=call({'action':'list'})['tasks'][0]
                if current['status'] in ('complete','error'):
                    break
                time.sleep(.1)
            self.assertEqual(current['status'],'complete', current.get('error'))
            self.assertEqual(hashlib.sha256(Path(current['output']).read_bytes()).hexdigest(), HASH)
            msg=json.dumps({'action':'ping'}).encode()
            result=subprocess.run([sys.executable,str(ROOT/'mdm.py'),'--native'],env=env,
                input=struct.pack('=I',len(msg))+msg,capture_output=True,timeout=5)
            size=struct.unpack('=I',result.stdout[:4])[0]
            self.assertEqual(size,len(result.stdout)-4)
            self.assertTrue(json.loads(result.stdout[4:])['ok'])
            msg=json.dumps({'action':'settings','settings':{'folder':'/tmp'}}).encode()
            result=subprocess.run([sys.executable,str(ROOT/'mdm.py'),'--native'],env=env,
                input=struct.pack('=I',len(msg))+msg,capture_output=True,timeout=5)
            self.assertFalse(json.loads(result.stdout[4:])['ok'])
            endpoint=json.loads((state/'endpoint.json').read_text())
            self.assertEqual(len(endpoint['token']),64)
        finally:
            p.terminate()
            p.wait(timeout=30)
            p.stderr.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
