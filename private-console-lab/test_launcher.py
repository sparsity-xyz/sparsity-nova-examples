"""Negative archive tests and an actual HTTP authenticated-channel round trip."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.key = X25519PrivateKey.generate()
        pub = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        (root / 'policy.json').write_text(json.dumps({'client_public_key': base64.b64encode(pub).decode(), 'package_sha256': '0' * 64}))
        (root / 'launcher.py').write_bytes(Path(__file__).with_name('launcher.py').read_bytes())
        spec = importlib.util.spec_from_file_location('launcher_under_test', root / 'launcher.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)

    def tearDown(self):
        self.temp.cleanup()

    def test_wrong_package_hash(self):
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.module.install_package(b'not-approved')

    def test_pinned_archive_still_rejects_path_traversal_and_links(self):
        for name, kind in [('opt/nova/../../escape', tarfile.REGTYPE), ('lab/bootstrap.py', tarfile.SYMTYPE)]:
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode='w:gz') as archive:
                member = tarfile.TarInfo(name); member.type = kind; member.linkname = '/etc/passwd'
                archive.addfile(member)
            content = raw.getvalue()
            self.module.POLICY['package_sha256'] = hashlib.sha256(content).hexdigest()
            with self.assertRaisesRegex(ValueError, 'member'):
                self.module.install_package(content)

    def test_authenticated_response_replay_rejection_and_wrong_key(self):
        m = self.module
        m.execute = lambda q: {'echo': q['value']}
        server = m.ThreadingHTTPServer(('127.0.0.1', 0), m.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            shared = self.key.exchange(X25519PublicKey.from_public_bytes(m.PUBLIC))
            def derive(label):
                return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=label.encode()).derive(shared)
            rx = derive('nova-console-lab-client-to-server'); tx = derive('nova-console-lab-server-to-client')
            nonce = os.urandom(12)
            ciphertext = AESGCM(rx).encrypt(nonce, m.canonical({'value': 'synthetic-message'}), m.BOOT.encode())
            def post(blob):
                req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/secure',
                    data=m.canonical({'nonce': base64.b64encode(nonce).decode(), 'ciphertext': base64.b64encode(blob).decode()}),
                    headers={'Content-Type': 'application/json'})
                return urllib.request.urlopen(req, timeout=5)
            with post(ciphertext) as response:
                envelope = json.load(response)
            plain = AESGCM(tx).decrypt(base64.b64decode(envelope['nonce']), base64.b64decode(envelope['ciphertext']), m.BOOT.encode() + nonce)
            self.assertEqual(json.loads(plain), {'ok': True, 'result': {'echo': 'synthetic-message'}})
            with self.assertRaises(urllib.error.HTTPError) as error:
                post(ciphertext)
            self.assertEqual(error.exception.code, 400)
            wrong = AESGCM(os.urandom(32)).encrypt(nonce, b'{}', m.BOOT.encode())
            with self.assertRaises(urllib.error.HTTPError) as error:
                post(wrong)
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
