import importlib.util, os, tempfile, unittest
from pathlib import Path
from cryptography.exceptions import InvalidTag
spec=importlib.util.spec_from_file_location('backup_app',Path(__file__).with_name('app.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();m.HOST=Path(self.tmp.name);m.PLAIN=m.HOST
        self.lab=m.Lab();self.lab.key=os.urandom(32);self.lab.dataset='test';self.lab.prefix='test/'
        self.lab.db=m.HOST/'db.sqlite3';self.lab.create(self.lab.db);self.objects={}
        self.lab.put=lambda k,v:self.objects.__setitem__(k,v);self.lab.get=lambda k:self.objects[k]
        def stats():
            c=m.connect(self.lab.db)
            try:return {'seq':self.lab.head(c)[0],'accounts':list(c.execute('SELECT * FROM accounts')),'integrity':c.execute('PRAGMA integrity_check').fetchone()[0]}
            finally:c.close()
        self.lab.stats=stats
    def tearDown(self):self.tmp.cleanup()
    def test_retry_after_local_commit_publishes_once_without_double_debit(self):
        q={'txid':'a','sender':1,'receiver':2,'amount':50}
        self.assertFalse(self.lab.transfer(dict(q,fail_after_commit=True))['acknowledged'])
        self.assertEqual(len(self.objects),0)
        self.assertTrue(self.lab.transfer(q)['duplicate']);self.assertEqual(len(self.objects),1)
        self.assertTrue(self.lab.transfer(q)['duplicate']);self.assertEqual(len(self.objects),1)
        self.assertEqual(self.lab.stats()['accounts'],[(1,'Alice',9950),(2,'Bob',5050),(3,'Carol',2500)])
        with self.assertRaises(AssertionError):self.lab.transfer(dict(q,amount=60))
    def test_aead_rejects_tamper_wrong_sequence_and_wrong_key(self):
        blob=self.lab.encrypt(b'synthetic secret','journal',1)
        self.assertEqual(self.lab.decrypt(blob,'journal',1),b'synthetic secret')
        with self.assertRaises(InvalidTag):self.lab.decrypt(blob[:-1]+bytes([blob[-1]^1]),'journal',1)
        with self.assertRaises(InvalidTag):self.lab.decrypt(blob,'journal',2)
        self.lab.key=os.urandom(32)
        with self.assertRaises(InvalidTag):self.lab.decrypt(blob,'journal',1)

if __name__=='__main__':unittest.main()
