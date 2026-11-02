"""Synthetic SQLite enclave example. No arbitrary SQL or runtime-key API."""
import base64
import hashlib
from html import escape
import json
import os
from pathlib import Path
import sqlite3
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path('/mnt/appdata')


def experiment():
    # Refuse a silent fallback to the enclave's volatile root filesystem.
    assert ROOT.is_mount(), 'Capsule hostfs must be mounted at /mnt/appdata'
    db = ROOT / ('sqlite-basic-' + uuid.uuid4().hex + '.sqlite3')
    c = sqlite3.connect(db, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.executescript(Path('/app/queries.sql').read_text())
    queries = {
        'accounts': 'SELECT name, balance_cents FROM accounts ORDER BY id',
        'transfers': '''SELECT t.id, a.name AS sender, b.name AS receiver, t.amount_cents
                        FROM transfers t JOIN accounts a ON a.id=t.sender_id
                        JOIN accounts b ON b.id=t.receiver_id ORDER BY t.id''',
        'totals': 'SELECT COUNT(*) AS accounts, SUM(balance_cents) AS total_cents FROM accounts',
        'sent_by_person': '''SELECT a.name, SUM(t.amount_cents) AS sent_cents
                             FROM transfers t JOIN accounts a ON a.id=t.sender_id
                             GROUP BY a.id, a.name ORDER BY a.id''',
    }
    results = {name: {'sql': sql, 'rows': [dict(r) for r in c.execute(sql)]}
               for name, sql in queries.items()}
    assert results['accounts']['rows'] == [
        {'name': 'Alice', 'balance_cents': 8750},
        {'name': 'Bob', 'balance_cents': 5750},
        {'name': 'Carol', 'balance_cents': 3000},
    ]
    assert results['totals']['rows'] == [{'accounts': 3, 'total_cents': 17500}]
    assert results['sent_by_person']['rows'] == [
        {'name': 'Alice', 'sent_cents': 1250}, {'name': 'Bob', 'sent_cents': 500}]
    assert results['transfers']['rows'] == [
        {'id': 1, 'sender': 'Alice', 'receiver': 'Bob', 'amount_cents': 1250},
        {'id': 2, 'sender': 'Bob', 'receiver': 'Carol', 'amount_cents': 500}]
    integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
    assert integrity == 'ok'
    pragmas = {key: c.execute('PRAGMA ' + key).fetchone()[0]
               for key in ['journal_mode', 'synchronous', 'page_size', 'page_count', 'cache_size']}
    c.close()
    with sqlite3.connect(db) as reopened:
        assert reopened.execute('SELECT SUM(balance_cents) FROM accounts').fetchone()[0] == 17500
    st = os.statvfs(ROOT)
    return {
        'status': 'PASS', 'captured_at_unix': time.time(),
        'sqlite_version': sqlite3.sqlite_version, 'database_path': str(db),
        'database_bytes': db.stat().st_size,
        'database_sha256': hashlib.sha256(db.read_bytes()).hexdigest(),
        'hostfs_mount': [line for line in Path('/proc/mounts').read_text().splitlines()
                         if line.split()[1] == str(ROOT)],
        'filesystem_capacity_bytes': st.f_frsize * st.f_blocks,
        'pragmas': pragmas, 'queries': results, 'integrity_check': integrity,
        'checks': ['create tables', 'insert', 'update', 'delete', 'transaction commit',
                   'transaction rollback', 'join', 'group by', 'sum', 'close/reopen',
                   'integrity_check'],
        'source_scope': 'Public synthetic example; no private application data',
        'storage_scope': 'Plain hostfs with synthetic data; not an encrypted database',
        'not_tested': ['backup', 'restore', 'crash recovery', 'rollback attacks', 'KMS'],
    }


RESULT = experiment()
BODY = json.dumps(RESULT, sort_keys=True, separators=(',', ':')).encode()
BODY_HASH = hashlib.sha256(BODY).hexdigest()
print(json.dumps({'event': 'sqlite-complete', 'status': RESULT['status'],
                  'result_sha256': BODY_HASH}), flush=True)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == '/':
            sections = ''.join('<section><h2>' + escape(name.replace('_', ' ').title())
                               + '</h2><pre>' + escape(query['sql']) + '</pre><pre>'
                               + escape(json.dumps(query['rows'], indent=2)) + '</pre></section>'
                               for name, query in RESULT['queries'].items())
            page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>SQLite inside Nitro</title><style>'
                    'body{font:16px system-ui;background:#101827;color:#edf3fb;margin:0;padding:32px}'
                    'main{max-width:900px;margin:auto}section{background:#19263a;padding:20px;'
                    'border-radius:12px;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
                    'background:#0c1420;padding:14px}a{color:#83e0be}h1{margin-bottom:8px}'
                    '.pass{color:#83e0be}p{line-height:1.6}</style><main>'
                    '<p class="pass">SQL checks: PASS</p><h1>SQLite inside Nitro</h1>'
                    '<p>SQLite ' + escape(RESULT['sqlite_version']) + ' · Database '
                    + str(RESULT['database_bytes']) + ' bytes · Integrity check: ok</p>'
                    '<p>Database file: <code>' + escape(RESULT['database_path']) + '</code></p>'
                    '<p>SQLite executes inside the enclave. This example uses plain Capsule '
                    'hostfs and synthetic data; it does not encrypt the backing file.</p>'
                    '<p><a href="/result">Complete SQL results</a> · '
                    '<a href="/accounts">Run the accounts SELECT now</a></p>'
                    + sections + '</main></html>')
            return self.reply(200, page.encode(), 'text/html; charset=utf-8')
        if self.path == '/accounts':
            with sqlite3.connect(RESULT['database_path']) as connection:
                rows = connection.execute('SELECT name, balance_cents FROM accounts ORDER BY id').fetchall()
            return self.reply(200, json.dumps({'sqlite_version': sqlite3.sqlite_version,
                                              'rows': rows, 'queried_at_unix': time.time()}).encode())
        if self.path in ('/result', '/health'):
            return self.reply(200, BODY)
        self.reply(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path != '/attestation':
            return self.reply(404, b'{"error":"not found"}')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024:
                return self.reply(400, b'{"error":"invalid length"}')
            request = json.loads(self.rfile.read(length))
            nonce = base64.b64decode(request['nonce'], validate=True)
            if len(nonce) != 32:
                return self.reply(400, b'{"error":"expected 32-byte nonce"}')
            body = json.dumps({'nonce': request['nonce'],
                               'user_data': {'sqlite_result_sha256': BODY_HASH}}).encode()
            req = urllib.request.Request('http://127.0.0.1:18001/v1/attestation',
                                         data=body, headers={'Content-Type': 'application/json'})
            # This is an enclave-local runtime request; do not send it through egress.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=15) as r:
                self.reply(200, r.read(), 'application/cbor')
        except Exception:
            self.reply(502, b'{"error":"attestation unavailable"}')


ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
