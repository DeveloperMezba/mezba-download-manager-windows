"""Authenticated loopback IPC. No HTTP server, browser page access or pickle."""
import hmac
import json
import secrets
import socket
import socketserver
import threading
import time
from .common import STATE, atomic_json
MAX_MESSAGE=256*1024

def exchange(message,timeout):
    endpoint=json.loads((STATE/'endpoint.json').read_text())
    try:
        sock=socket.create_connection(('127.0.0.1',int(endpoint['port'])),timeout)
    except OSError as e:raise ConnectionRefusedError('MDM service is not running') from e
    with sock:
        sock.settimeout(timeout)
        payload=json.dumps({'token':endpoint['token'],'message':message}).encode()+b'\n'
        if len(payload)>MAX_MESSAGE:raise ValueError('Request too large')
        sock.sendall(payload)
        with sock.makefile('rb') as f:raw=f.readline(64*1024*1024)
    if not raw:raise RuntimeError('MDM service disconnected')
    response=json.loads(raw)
    if not response.get('ok'):raise RuntimeError(response.get('error','MDM request failed'))
    return response.get('result')

class Server(socketserver.ThreadingTCPServer):
    daemon_threads=True;allow_reuse_address=False

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(130)
        try:
            raw=self.rfile.readline(MAX_MESSAGE+1)
            if len(raw)>MAX_MESSAGE or not raw.endswith(b'\n'):raise ValueError('Invalid request length')
            envelope=json.loads(raw)
            token=envelope.get('token','')
            if not isinstance(token,str) or not hmac.compare_digest(token,self.server.token):raise ValueError('Unauthorized')
            message=envelope['message']
            if not isinstance(message,dict):raise ValueError('Invalid request')
            result=self.server.manager.dispatch(message)
            response={'ok':True,'result':result}
        except Exception as e:response={'ok':False,'error':str(e)}
        try:self.wfile.write(json.dumps(response).encode()+b'\n')
        except (BrokenPipeError,ConnectionResetError):pass

def run_server(manager):
    with Server(('127.0.0.1',0),Handler) as server:
        server.manager=manager;server.token=secrets.token_hex(32);server.timeout=.3
        atomic_json(STATE/'endpoint.json',{'port':server.server_address[1],'token':server.token})
        try:
            while not manager.closing.is_set():server.handle_request()
            with manager.lock:
                for event in manager.active.values():event.set()
            deadline=time.monotonic()+25
            while manager.active and time.monotonic()<deadline:time.sleep(.1)
        finally:
            (STATE/'endpoint.json').unlink(missing_ok=True)
            manager.closing.set()
