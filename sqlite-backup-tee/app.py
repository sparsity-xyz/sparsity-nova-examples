"""Bounded synthetic SQLite/S3 recovery lab. Keys enter over attested encrypted RPC."""
import base64, hashlib, json, os, re, signal, sqlite3, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HOST=Path('/mnt/appdata'); PLAIN=Path('/run/sqlite-backup-plain')
SERVER=X25519PrivateKey.generate()
PUBLIC=SERVER.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
CLIENT=base64.b64decode(Path(__file__).with_name('client-public.txt').read_text().strip())
BOOT=os.urandom(16).hex(); ZERO='0'*64

def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(v): return hashlib.sha256(v).hexdigest()
def derive(k,label): return HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=label.encode()).derive(k)
SHARED=SERVER.exchange(X25519PublicKey.from_public_bytes(CLIENT))
RX=derive(SHARED,'nova-sqlite-client-to-server'); TX=derive(SHARED,'nova-sqlite-server-to-client')

def local_api(path,data):
    req=urllib.request.Request('http://127.0.0.1:18000'+path,data=canonical(data),headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=90) as r: return r.read()

def connect(path):
    c=sqlite3.connect(path,isolation_level=None,timeout=10)
    c.execute('PRAGMA journal_mode=DELETE'); c.execute('PRAGMA synchronous=FULL')
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA cache_size=-2048')
    return c

class Lab:
    def __init__(self): self.ready=False; self.needs_restore=True; self.lock=threading.Lock(); self.seen=set(); self.report={}
    def initialize(self,cfg):
        if self.ready: raise ValueError('already initialized')
        if not HOST.is_mount(): raise ValueError('hostfs missing')
        self.key=base64.b64decode(cfg['data_key_b64'],validate=True); assert len(self.key)==32
        self.dataset=cfg['dataset']; assert re.fullmatch(r'[a-z0-9-]{1,80}',self.dataset)
        self.prefix='sqlite-lab/'+self.dataset+'/'
        self.contract=cfg['contract']; assert re.fullmatch(r'0x[0-9a-fA-F]{40}',self.contract)
        self.selector=cfg['latest_selector']; assert re.fullmatch(r'0x[0-9a-f]{8}',self.selector)
        cipher=HOST/'encrypted-db';cipher.mkdir(exist_ok=True); PLAIN.mkdir(exist_ok=True)
        password=derive(self.key,'nova-sqlite-gocryptfs').hex()
        keyfile=Path('/run/sqlite-backup.pass');keyfile.write_text(password+'\n');keyfile.chmod(0o600)
        try:
            if not (cipher/'gocryptfs.conf').exists():
                subprocess.run(['gocryptfs','-q','-init','-passfile',str(keyfile),str(cipher)],check=True,capture_output=True,timeout=90)
            subprocess.run(['gocryptfs','-q','-noprealloc','-passfile',str(keyfile),str(cipher),str(PLAIN)],check=True,capture_output=True,timeout=45)
        finally: keyfile.unlink(missing_ok=True)
        self.db=PLAIN/'service.sqlite3'
        self.create(self.db);self.ready=True
        # Round-trip ciphertext only; this checks actual S3 transport inside Nitro.
        raw=self.encrypt(b's3-encryption-probe','probe',0)
        k=self.prefix+'probe/'+sha(raw)+'.bin';self.put(k,raw);assert self.get(k)==raw
        self.needs_restore=self.chain()['epoch']>0
        return self.stats()
    def create(self,path):
        c=connect(path)
        c.executescript('CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,name TEXT,balance INTEGER CHECK(balance>=0)); CREATE TABLE IF NOT EXISTS operations(seq INTEGER PRIMARY KEY,txid TEXT UNIQUE,record TEXT,record_hash TEXT,s3_key TEXT,cipher BLOB,uploaded INTEGER); CREATE TABLE IF NOT EXISTS padding(id INTEGER PRIMARY KEY,value TEXT);')
        if c.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]==0:
            c.executemany('INSERT INTO accounts VALUES(?,?,?)',[(1,'Alice',10000),(2,'Bob',5000),(3,'Carol',2500)])
            c.execute('BEGIN');c.executemany('INSERT INTO padding VALUES(?,?)',[(i,'SQLITE_SECRET_MARKER_'+str(i)+'x'*4096) for i in range(64)]);c.execute('COMMIT')
        c.close()
    def put(self,k,raw):
        assert k.startswith(self.prefix) and '..' not in k
        v=json.loads(local_api('/v1/s3/put',{'key':k,'value':base64.b64encode(raw).decode(),'content_type':'application/octet-stream'}));assert v['success']
    def get(self,k):
        assert k.startswith(self.prefix) and '..' not in k
        return base64.b64decode(json.loads(local_api('/v1/s3/get',{'key':k}))['value'],validate=True)
    def encrypt(self,raw,kind,seq):
        nonce=os.urandom(12); aad=canonical([self.dataset,kind,seq])
        return b'NSQL1'+nonce+AESGCM(derive(self.key,'nova-sqlite-'+kind)).encrypt(nonce,raw,aad)
    def decrypt(self,blob,kind,seq):
        assert blob[:5]==b'NSQL1'
        return AESGCM(derive(self.key,'nova-sqlite-'+kind)).decrypt(blob[5:17],blob[17:],canonical([self.dataset,kind,seq]))
    def head(self,c):
        row=c.execute('SELECT seq,record_hash FROM operations ORDER BY seq DESC LIMIT 1').fetchone()
        return row if row else (0,ZERO)
    def publish(self,c):
        for seq,k,blob in c.execute('SELECT seq,s3_key,cipher FROM operations WHERE uploaded=0 ORDER BY seq').fetchall():
            self.put(k,blob);assert sha(self.get(k))==sha(blob)
            c.execute('UPDATE operations SET uploaded=1 WHERE seq=?',(seq,))
    def transfer(self,q):
        txid=q['txid']; assert re.fullmatch(r'[a-zA-Z0-9-]{1,80}',txid)
        sender,receiver,amount=q['sender'],q['receiver'],q['amount']
        assert all(type(x)==int for x in (sender,receiver,amount)) and sender in (1,2,3) and receiver in (1,2,3) and sender!=receiver and 0<amount<10000
        c=connect(self.db)
        try:
            old=c.execute('SELECT seq,record,s3_key FROM operations WHERE txid=?',(txid,)).fetchone()
            if old:
                r=json.loads(old[1]);assert (r['sender'],r['receiver'],r['amount'])==(sender,receiver,amount),'idempotency conflict'
                self.publish(c);return {'duplicate':True,'seq':old[0],'log_key':old[2],'stats':self.stats()}
            self.publish(c);c.execute('BEGIN IMMEDIATE');seq,prev=self.head(c);seq+=1
            r={'seq':seq,'txid':txid,'sender':sender,'receiver':receiver,'amount':amount,'previous':prev,'dataset':self.dataset}
            body=canonical(r);rh=sha(body);blob=self.encrypt(body,'journal',seq);key=self.prefix+f'logs/{seq:012d}-'+sha(blob)+'.bin'
            c.execute('UPDATE accounts SET balance=balance-? WHERE id=?',(amount,sender));c.execute('UPDATE accounts SET balance=balance+? WHERE id=?',(amount,receiver))
            c.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,0)',(seq,txid,body.decode(),rh,key,blob));c.execute('COMMIT')
            if q.get('fail_after_commit'): return {'injected_failure':'local commit succeeded, S3 not yet uploaded; retry same txid','acknowledged':False,'seq':seq}
            self.publish(c)
            return {'duplicate':False,'acknowledged':True,'seq':seq,'log_key':key,'stats':self.stats()}
        finally: c.close()
    def chain(self):
        payload={'jsonrpc':'2.0','id':1,'method':'eth_call','params':[{'to':self.contract,'data':self.selector},'latest']}
        req=urllib.request.Request('https://sepolia.base.org',data=canonical(payload),headers={'Content-Type':'application/json','User-Agent':'nova-sqlite-lab'})
        with urllib.request.urlopen(req,timeout=30) as r: v=json.loads(r.read())
        if 'error' in v:raise ValueError('chain RPC failed')
        raw=bytes.fromhex(v['result'][2:]);assert len(raw)==128
        return {'epoch':int.from_bytes(raw[:32]),'seq':int.from_bytes(raw[32:64]),'manifest_hash':raw[64:96].hex(),'log_head':raw[96:128].hex()}
    def checkpoint(self):
        c=connect(self.db)
        try:
            self.publish(c);seq,head=self.head(c);previous=self.chain()
            fd,tmp=tempfile.mkstemp(dir='/tmp',suffix='.sqlite3');os.close(fd)
            try:
                dest=sqlite3.connect(tmp);c.backup(dest);assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok';dest.close()
                raw=Path(tmp).read_bytes()
            finally:Path(tmp).unlink(missing_ok=True)
            blob=self.encrypt(raw,'snapshot',seq);digest=sha(blob);key=self.prefix+'snapshots/'+digest+'.bin'
            self.put(key,blob);assert sha(self.get(key))==digest
            manifest={'schema':1,'dataset':self.dataset,'chain_id':84532,'contract':self.contract.lower(),'epoch':previous['epoch']+1,'seq':seq,'log_head':head,'previous_manifest':previous['manifest_hash'],'snapshot_key':key,'ciphertext_sha256':digest,'database_bytes':len(raw),'ciphertext_bytes':len(blob)}
            data=canonical(manifest);mh=sha(data);mk=self.prefix+'manifests/'+mh+'.json';self.put(mk,data);assert self.get(mk)==data
            return {'manifest':manifest,'manifest_hash':mh,'manifest_key':mk,'uploaded_and_readback_verified':True,'onchain_committed':False}
        finally:c.close()
    def restore(self,q):
        latest=self.chain();mh=q.get('manifest_hash',latest['manifest_hash'])
        if mh!=latest['manifest_hash']:raise ValueError('rollback rejected: requested manifest is not chain latest')
        if mh==ZERO:raise ValueError('no anchored checkpoint')
        data=self.get(self.prefix+'manifests/'+mh+'.json');assert sha(data)==mh,'manifest tampered'
        m=json.loads(data);assert m['dataset']==self.dataset and m['contract']==self.contract.lower() and m['chain_id']==84532
        assert (m['epoch'],m['seq'],m['log_head'])==(latest['epoch'],latest['seq'],latest['log_head'])
        blob=self.get(m['snapshot_key']);assert sha(blob)==m['ciphertext_sha256'],'ciphertext hash mismatch'
        if q.get('tamper_test'):blob=blob[:-1]+bytes([blob[-1]^1])
        raw=self.decrypt(blob,'snapshot',m['seq'])
        path=PLAIN/('restored-'+uuid.uuid4().hex+'.sqlite3');path.write_bytes(raw)
        with path.open('rb') as f:os.fsync(f.fileno())
        c=connect(path)
        try:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert self.head(c)==(m['seq'],m['log_head'])
        finally:c.close()
        # Publish the new DB only after verification. Historical test files remain.
        old=str(self.db);self.db=path;self.needs_restore=False
        return {'restored_from_s3':True,'old_database':old,'new_database':str(path),'anchor':latest,'stats':self.stats()}
    def replay(self,q):
        c=connect(self.db);applied=0;duplicates=0
        try:
            for item in q['logs']:
                seq=item['seq'];key=item['log_key'];blob=self.get(key);r=json.loads(self.decrypt(blob,'journal',seq));rh=sha(canonical(r))
                assert r['dataset']==self.dataset and r['seq']==seq
                old=c.execute('SELECT record_hash FROM operations WHERE txid=?',(r['txid'],)).fetchone()
                if old:assert old[0]==rh;duplicates+=1;continue
                head_seq,head=self.head(c);assert seq==head_seq+1 and r['previous']==head,'journal gap or wrong chain'
                c.execute('BEGIN IMMEDIATE')
                c.execute('UPDATE accounts SET balance=balance-? WHERE id=?',(r['amount'],r['sender']))
                c.execute('UPDATE accounts SET balance=balance+? WHERE id=?',(r['amount'],r['receiver']))
                c.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,1)',(seq,r['txid'],canonical(r).decode(),rh,key,blob));c.execute('COMMIT');applied+=1
            return {'applied':applied,'duplicates':duplicates,'tail_freshness':'requires client receipt or newer external anchor','stats':self.stats()}
        finally:c.close()
    def crash_writer(self):
        before=self.stats()
        script="""import sqlite3,sys,time
c=sqlite3.connect(sys.argv[1],isolation_level=None)
c.execute('PRAGMA journal_mode=DELETE');c.execute('PRAGMA synchronous=FULL');c.execute('PRAGMA cache_size=8')
c.execute('BEGIN IMMEDIATE');c.execute('UPDATE accounts SET balance=0');c.execute("UPDATE padding SET value=replace(value,'x','y')")
print('uncommitted',flush=True);time.sleep(60)
"""
        p=subprocess.Popen([sys.executable,'-u','-c',script,str(self.db)],stdout=subprocess.PIPE,text=True)
        try:
            assert p.stdout.readline().strip()=='uncommitted';os.kill(p.pid,signal.SIGKILL);p.wait(timeout=10)
        finally:
            if p.poll() is None:p.kill();p.wait()
        after=self.stats();assert before['accounts']==after['accounts'] and before['seq']==after['seq'] and after['integrity']=='ok'
        return {'writer_exit':p.returncode,'rolled_back_uncommitted_changes':True,'stats':after,'scope':'writer SIGKILL, not host power loss'}
    def stats(self):
        c=connect(self.db)
        try:
            accounts=[{'id':r[0],'name':r[1],'balance_cents':r[2]} for r in c.execute('SELECT * FROM accounts ORDER BY id')];seq,head=self.head(c)
            pending=c.execute('SELECT COUNT(*) FROM operations WHERE uploaded=0').fetchone()[0]
            integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        finally:c.close()
        v=os.statvfs(HOST)
        return {'accounts':accounts,'seq':seq,'log_head':head,'pending_s3_logs':pending,'integrity':integrity,'sqlite_version':sqlite3.sqlite_version,'database_bytes':self.db.stat().st_size,'database_path':str(self.db),'hostfs_capacity_bytes':v.f_frsize*v.f_blocks,'hostfs_available_bytes':v.f_frsize*v.f_bavail,'encryption':'gocryptfs live database; AES-256-GCM snapshots and journal objects','mounts':[l for l in Path('/proc/mounts').read_text().splitlines() if l.split()[1] in (str(HOST),str(PLAIN))],'memory_kib':{l.split(':')[0]:l.split(':')[1].strip() for l in Path('/proc/meminfo').read_text().splitlines() if l.split(':')[0] in ('MemTotal','MemAvailable','SwapTotal')},'pid':os.getpid()}
    def run(self,q):
        action=q['action']
        if action=='initialize':return self.initialize(q)
        if not self.ready:raise ValueError('initialize first')
        if action=='stats':return self.stats()
        if self.needs_restore and action not in ('restore','chain'):
            raise ValueError('restore the latest on-chain checkpoint before writes after restart')
        if action=='transfer':return self.transfer(q)
        if action=='checkpoint':return self.checkpoint()
        if action=='restore':return self.restore(q)
        if action=='replay':return self.replay(q)
        if action=='crash_writer':return self.crash_writer()
        if action=='chain':return self.chain()
        raise ValueError('unknown action')

LAB=Lab()
class Handler(BaseHTTPRequestHandler):
    def reply(self,status,body,ct='application/json'):
        self.send_response(status);self.send_header('Content-Type',ct);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/identity':return self.reply(200,canonical({'server_public_b64':base64.b64encode(PUBLIC).decode(),'boot':BOOT}))
        if self.path=='/':
            with LAB.lock:
                state=LAB.stats() if LAB.ready else {'state':'awaiting authenticated initialization'}
            # Synthetic public dashboard only; modification and backup APIs are encrypted/authenticated.
            from html import escape
            body=('<!doctype html><html><meta charset="utf-8"><title>Encrypted SQLite recovery lab</title><style>body{background:#101827;color:#eaf4ff;font:16px system-ui;padding:32px}main{max-width:1000px;margin:auto}pre{background:#1b2c43;padding:20px;white-space:pre-wrap}h1{color:#80e1bb}</style><main><h1>SQLite + encrypted S3 backups</h1><p>Real Nitro enclave · encrypted disk · synthetic accounts</p><pre>'+escape(json.dumps(state,indent=2))+'</pre><p>Only the authorized encrypted client can submit transactions, checkpoint or restore.</p></main></html>').encode()
            return self.reply(200,body,'text/html; charset=utf-8')
        if self.path=='/health':return self.reply(200,canonical({'alive':True,'initialized':LAB.ready}))
        return self.reply(404,b'{}')
    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0'));assert 0<n<16384
            q=json.loads(self.rfile.read(n))
            if self.path=='/attestation':
                nonce=base64.b64decode(q['nonce'],validate=True);assert len(nonce)==32
                body=local_api('/v1/attestation',{'nonce':q['nonce'],'user_data':{'sqlite_server_key_sha256':sha(PUBLIC),'boot':BOOT}})
                return self.reply(200,body,'application/cbor')
            if self.path!='/rpc':return self.reply(404,b'{}')
            nonce=base64.b64decode(q['nonce'],validate=True);assert len(nonce)==12
            command=json.loads(AESGCM(RX).decrypt(nonce,base64.b64decode(q['ciphertext'],validate=True),BOOT.encode()))
            with LAB.lock:
                assert nonce not in LAB.seen,'replayed request';assert len(LAB.seen)<2048
                LAB.seen.add(nonce);start=time.monotonic()
                try: result={'ok':True,'result':LAB.run(command)}
                except Exception as e: result={'ok':False,'error':type(e).__name__,'detail':str(e)[:180]}
                result['elapsed_seconds']=round(time.monotonic()-start,4)
                LAB.report[command.get('action','?')]=result.get('ok')
            out_nonce=os.urandom(12)
            payload=AESGCM(TX).encrypt(out_nonce,canonical(result),BOOT.encode()+nonce)
            self.reply(200,canonical({'nonce':base64.b64encode(out_nonce).decode(),'ciphertext':base64.b64encode(payload).decode()}))
        except Exception:self.reply(400,b'{"error":"invalid authenticated request"}')
    def log_message(self,*args):pass
if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
