"""Attested one-client lab launcher. Public image contains no private application source.

Only the exact SHA-256-pinned package can be installed. Package upload and HTTP
forwarding are authenticated/encrypted end-to-end, including through Nova's proxy.
This is an ephemeral compatibility lab, not a general hosting/security product.
"""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import threading
import time
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import requests

POLICY = json.loads(Path(__file__).with_name('policy.json').read_text())
SERVER = X25519PrivateKey.generate()
PUBLIC = SERVER.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
BOOT = os.urandom(16).hex()
SHARED = SERVER.exchange(X25519PublicKey.from_public_bytes(base64.b64decode(POLICY['client_public_key'])))


def derive(label):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=label.encode()).derive(SHARED)


RX = derive('nova-console-lab-client-to-server')
TX = derive('nova-console-lab-server-to-client')
LOCK = threading.Lock()
SEEN = set()
PROCESS = None
LOADED = None
SESSION = requests.Session()
SESSION.trust_env = False
STATE = Path('/run/nova-console-lab')


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()


def install_package(raw):
    global PROCESS, LOADED
    digest = hashlib.sha256(raw).hexdigest()
    if digest != POLICY['package_sha256']:
        raise ValueError('Package digest is not approved')
    if LOADED:
        return {'already_loaded': True, 'package_sha256': LOADED}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if not 1 <= len(members) <= 256 or sum(m.size for m in members) > 16 * 1024 * 1024:
            raise ValueError('Invalid archive bounds')
        names = set()
        for member in members:
            p = PurePosixPath(member.name)
            if (not member.isfile() or p.is_absolute() or '..' in p.parts or member.name in names
                    or not (member.name.startswith('opt/nova/') or member.name in ('lab/bootstrap.py', 'lab/sidecar.py'))):
                raise ValueError('Invalid package member')
            names.add(member.name)
            if Path('/' + member.name).exists():
                raise ValueError('Package would overwrite existing file')
        for member in members:
            destination = Path('/' + member.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(member).read())
            destination.chmod(0o600)
    env = {**os.environ, 'PYTHONPATH': '/opt/nova:/opt/nova/control-plane'}
    with open('/run/console-bootstrap.log', 'wb') as log:
        PROCESS = subprocess.Popen(['python', '-u', '/lab/bootstrap.py'], env=env,
                                   cwd='/opt/nova', stdout=log, stderr=subprocess.STDOUT)
    LOADED = digest
    return {'loaded': True, 'package_sha256': digest, 'pid': PROCESS.pid}


def execute(command):
    action = command['action']
    if action == 'install':
        return install_package(base64.b64decode(command['package_base64'], validate=True))
    if action == 'status':
        result = {'loaded_package_sha256': LOADED, 'process_exit_code': None if PROCESS is None else PROCESS.poll()}
        try:
            result['console'] = SESSION.get('http://127.0.0.1:8081/status', timeout=5).json()
        except requests.RequestException:
            result['console'] = None
        # Diagnostics only over the authenticated channel; no source files or credentials.
        result['logs'] = {}
        for name, path in [('bootstrap', Path('/run/console-bootstrap.log'))] + [(x, STATE / (x + '.log')) for x in ('mariadb', 'console', 'orchestrator')]:
            if path.exists():
                result['logs'][name] = path.read_text(errors='replace')[-12000:]
        return result
    if action == 'http':
        method = command.get('method', 'GET')
        path = command['path']
        if method not in ('GET', 'HEAD', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'):
            raise ValueError('Method not supported')
        if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or '\\' in path or '#' in path:
            raise ValueError('Invalid relative request path')
        headers = {k: v for k, v in command.get('headers', {}).items()
                   if k.lower() in ('authorization', 'content-type', 'accept', 'cookie')}
        response = SESSION.request(method, 'https://localhost:8443' + path, headers=headers,
             data=base64.b64decode(command.get('body_base64', ''), validate=True),
             verify=str(STATE / 'tls-cert.pem'), timeout=30, allow_redirects=False)
        if len(response.content) > 4 * 1024 * 1024:
            raise ValueError('Response exceeds laboratory limit')
        return {'status': response.status_code,
                'headers': {k: v for k, v in response.headers.items()
                            if k.lower() in ('content-type', 'content-security-policy', 'location', 'set-cookie', 'cache-control')},
                'body_base64': base64.b64encode(response.content).decode()}
    raise ValueError('Unknown command')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, body, mime='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/', '/health'):
            return self.reply(200, canonical({'service': 'Isolated private console lab', 'in_nitro': Path('/dev/nsm').exists(),
                'status': 'package_loaded' if LOADED else 'awaiting_authorized_package',
                'note': 'Console access requires the authorized encrypted client.'}))
        if self.path == '/identity':
            return self.reply(200, canonical({'server_public_key': base64.b64encode(PUBLIC).decode(),
                                              'boot': BOOT, 'package_sha256': POLICY['package_sha256']}))
        return self.reply(404, b'{}')

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4 * 1024 * 1024:
                return self.reply(413, b'{}')
            q = json.loads(self.rfile.read(size))
            if self.path == '/attestation':
                nonce = base64.b64decode(q['nonce'], validate=True)
                if len(nonce) != 32:
                    raise ValueError('Invalid challenge')
                req = urllib.request.Request('http://127.0.0.1:18000/v1/attestation',
                    # Bind the key in NSM's public_key field, not caller-supplied user_data alone.
                    # Capsule's external Aux API strips public_key overrides.
                    data=canonical({'nonce': q['nonce'],
                        'public_key': SERVER.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
                        'user_data': {
                        'console_loader_key_sha256': hashlib.sha256(PUBLIC).hexdigest(),
                        'boot': BOOT, 'package_sha256': POLICY['package_sha256']}}),
                    headers={'Content-Type': 'application/json'})
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as r:
                    return self.reply(200, r.read(), 'application/cbor')
            if self.path != '/secure':
                return self.reply(404, b'{}')
            nonce = base64.b64decode(q['nonce'], validate=True)
            if len(nonce) != 12:
                raise ValueError('Invalid nonce')
            command = json.loads(AESGCM(RX).decrypt(nonce, base64.b64decode(q['ciphertext'], validate=True), BOOT.encode()))
            with LOCK:
                if nonce in SEEN or len(SEEN) >= 4096:
                    raise ValueError('Replayed request or request budget exhausted')
                SEEN.add(nonce)
                try:
                    result = {'ok': True, 'result': execute(command)}
                except Exception as error:
                    result = {'ok': False, 'error': type(error).__name__ + ': ' + str(error)}
            out_nonce = os.urandom(12)
            payload = AESGCM(TX).encrypt(out_nonce, canonical(result), BOOT.encode() + nonce)
            return self.reply(200, canonical({'nonce': base64.b64encode(out_nonce).decode(), 'ciphertext': base64.b64encode(payload).decode()}))
        except Exception:
            return self.reply(400, b'{"error":"invalid or unauthorized request"}')


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
