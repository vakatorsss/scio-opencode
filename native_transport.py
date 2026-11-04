"""Schema-only MCP discovery and a temporary public tunnel.

This endpoint NEVER executes tools or returns local file contents. Actual tools
run in the local client after permission checks, or in OpenCode itself.
"""
import hashlib
from collections import deque
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

import scio_console as scio


class Discovery:
    def __init__(self, port=0):
        self.registries = {}
        self.requests = deque(maxlen=1000)
        self.lock = threading.RLock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, status, value=None):
                data = json.dumps(value).encode() if value is not None else b''
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self): self.reply(405)
            def do_DELETE(self): self.reply(200, {})
            def do_POST(self):
                with owner.lock: registry = owner.registries.get(self.path)
                if registry is None: return self.reply(404)
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1_000_000: return self.reply(413)
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict) or body.get('jsonrpc') != '2.0': return self.reply(400)
                    if 'id' not in body: return self.reply(202)
                    method = body.get('method')
                    owner.requests.append(method)
                    if method == 'initialize':
                        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'scio-local-tool-discovery', 'version': '1.0.0'}}
                    elif method == 'tools/list': result = {'tools': registry}
                    elif method == 'tools/call':
                        result = {'content': [{'type': 'text', 'text': 'LOCAL_EXECUTION_REQUIRED: the local client will execute this tool and submit its real result.'}], 'isError': True}
                    elif method == 'ping': result = {}
                    else: return self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'error': {'code': -32601, 'message': 'Method not found'}})
                    self.reply(200, {'jsonrpc': '2.0', 'id': body['id'], 'result': result})
                except (ValueError, TypeError, KeyError): self.reply(400)

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self): return self.server.server_port

    def register(self, tools):
        path = '/' + secrets.token_urlsafe(32) + '/mcp'
        with self.lock: self.registries[path] = tools
        return path

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


_binary_lock = threading.Lock()


def cloudflared_binary(explicit=None):
    # Multiple sessions may make their first connection together.
    with _binary_lock:
        return _cloudflared_binary(explicit)


def _cloudflared_binary(explicit=None):
    if explicit:
        path = Path(explicit).resolve(strict=True)
        if not path.is_file(): raise ValueError('cloudflared path must name a file')
        return str(path)
    if scio.DIST_DIR:
        path = scio.DIST_DIR / 'bin' / 'cloudflared.exe'
        manifest = json.loads((scio.DIST_DIR / 'distribution.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['cloudflared']['sha256']:
            raise RuntimeError('Bundled tunnel verification failed; extract a fresh SCIO CODE distribution.')
        return str(path)
    installed = shutil.which('cloudflared')
    if installed: return installed
    system = platform.system().lower()
    arch = 'arm64' if platform.machine().lower() in ('arm64','aarch64') else 'amd64'
    if system not in ('windows', 'linux'):
        raise RuntimeError('Install cloudflared first (macOS: brew install cloudflared).')
    name = f'cloudflared-{system}-{arch}' + ('.exe' if system == 'windows' else '')
    directory = scio.DATA_DIR / 'bin'
    directory.mkdir(parents=True, exist_ok=True)
    path, checksum = directory / name, directory / (name + '.sha256')
    if path.exists() and checksum.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum.read_text().strip(): return str(path)
    request = Request('https://api.github.com/repos/cloudflare/cloudflared/releases/latest', headers={'User-Agent': 'scio-opencode-native'})
    with urlopen(request, timeout=30) as response: release = json.load(response)
    asset = next((a for a in release['assets'] if a['name'] == name), None)
    if not asset or not (asset.get('digest') or '').startswith('sha256:'):
        raise RuntimeError('No verifiable cloudflared release asset; install it yourself and pass --cloudflared PATH.')
    with urlopen(asset['browser_download_url'], timeout=120) as response: data = response.read(150_000_001)
    digest = hashlib.sha256(data).hexdigest()
    if len(data) > 150_000_000 or digest != asset['digest'].split(':',1)[1]: raise RuntimeError('cloudflared checksum mismatch')
    path.write_bytes(data)
    checksum.write_text(digest)
    if os.name != 'nt': path.chmod(0o700)
    return str(path)


class Tunnel:
    def __init__(self, port, binary=None):
        executable = cloudflared_binary(binary)
        self.process = subprocess.Popen([executable, 'tunnel', '--url', f'http://127.0.0.1:{port}', '--http-host-header', f'127.0.0.1:{port}', '--no-autoupdate'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.url = None
        self.ready = threading.Event()
        def consume():
            for line in self.process.stdout:
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
                if match: self.url = match.group(0)
                if 'Registered tunnel connection' in line and self.url: self.ready.set()
        self.thread = threading.Thread(target=consume, daemon=True)
        self.thread.start()
        if not self.ready.wait(55):
            self.close()
            raise RuntimeError('Temporary tunnel could not connect within 55 seconds. Check your network, or use --public-url with your own HTTPS relay.')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
        self.thread.join(timeout=2)


class NativeRuntime:
    def __init__(self, cloudflared=None, public_url=None, discovery_port=0):
        if public_url and not discovery_port: raise ValueError('--public-url requires a fixed --discovery-port for your reverse proxy')
        self.discovery = Discovery(discovery_port)
        self.tunnel = None
        try:
            if public_url:
                if not public_url.startswith('https://'): raise ValueError('Public discovery URL must be HTTPS')
                self.url = public_url.rstrip('/')
            else:
                self.tunnel = Tunnel(self.discovery.port, cloudflared)
                self.url = self.tunnel.url
        except BaseException:
            self.discovery.close()
            raise

    def register(self, tools):
        # NativeClient.prepare verifies discovery from Scio's network using a
        # harmless native readiness call. Local DNS may block trycloudflare.com.
        return self.url + self.discovery.register(tools)

    def close(self):
        if self.tunnel: self.tunnel.close()
        self.discovery.close()
