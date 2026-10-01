from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from auth import PasswordAuth


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.password_file = Path(cls.temp.name)/'password.txt'
        cls.password_file.write_text('test-password-only\n',encoding='utf-8')
        with patch.dict(os.environ, ATELIER_DATA=cls.temp.name, ATELIER_PASSWORD_FILE=str(cls.password_file), ATELIER_COOKIE_SECURE='false'):
            spec = importlib.util.spec_from_file_location('atelier_auth_test_server', ROOT/'app/server.py')
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
        cls.http = cls.module.ThreadingHTTPServer(('127.0.0.1',0),cls.module.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.temp.cleanup()

    def setUp(self):
        with self.module.AUTH.lock:
            self.module.AUTH.sessions.clear();self.module.AUTH.failures.clear()
        self.jar = CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def post(self, path, data=None, extra=None, client=None):
        request = urllib.request.Request(self.base+path,json.dumps(data or {}).encode(),{'X-Atelier':'1',**(extra or {})})
        return (client or self.client).open(request)

    def sid(self):
        return next(c.value for c in self.jar if c.name=='atelier')

    def login(self):
        self.client.open(self.base).read()
        return self.post('/auth/login',dict(password='test-password-only'))

    def test_all_private_routes_require_password_even_with_anonymous_cookie(self):
        self.assertIn('Kennwort'.encode(),self.client.open(self.base).read())
        for path in ['/app.js','/color-tools.js','/api/projects','/api/original?id='+'a'*32,'/api/project?id='+'a'*32]:
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as e:self.client.open(self.base+path)
                self.assertEqual(e.exception.code,401)
        for path in ['/api/demo','/api/upload','/api/preview','/api/export','/auth/logout']:
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as e:self.post(path)
                self.assertEqual(e.exception.code,401)
        self.assertEqual(json.load(self.client.open(self.base+'/api/health')),dict(ok=True))
        self.assertIn(b'loginForm',self.client.open(self.base+'/login.js').read())

    def test_login_rotates_cookie_and_rejects_replay_after_logout(self):
        self.client.open(self.base).read();before=self.sid()
        response=self.login();cookie=response.headers['Set-Cookie'];response.read()
        self.assertNotEqual(before,self.sid())
        for flag in ['HttpOnly','SameSite=Lax','Path=/','Max-Age=43200']:self.assertIn(flag,cookie)
        self.assertIn(b'Motive vorbereiten',self.client.open(self.base).read())
        self.assertIsInstance(json.load(self.client.open(self.base+'/api/projects')),list)
        self.assertIn(b'ColorTools',self.client.open(self.base+'/color-tools.js').read())
        authenticated=self.sid()
        response=self.post('/auth/logout');self.assertIn('Max-Age=0',response.headers['Set-Cookie']);response.read()
        for old in [before,authenticated]:
            request=urllib.request.Request(self.base+'/api/projects',headers={'Cookie':'atelier='+old})
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(request)
            self.assertEqual(e.exception.code,401)
        self.assertIn('Kennwort'.encode(),self.client.open(self.base).read())

    def test_login_needs_cookie_and_same_origin_custom_header(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/auth/login',dict(password='test-password-only'))
        self.assertEqual(e.exception.code,403)
        self.client.open(self.base).read()
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/auth/login',dict(password='test-password-only'),{'Origin':'https://evil.example'})
        self.assertEqual(e.exception.code,403)
        request=urllib.request.Request(self.base+'/auth/login',b'{"password":"test-password-only"}')
        with self.assertRaises(urllib.error.HTTPError) as e:self.client.open(request)
        self.assertEqual(e.exception.code,403)
        self.login().read()
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/auth/logout',extra={'Origin':'https://evil.example'})
        self.assertEqual(e.exception.code,403)
        self.assertTrue(self.module.AUTH.valid(self.sid()))

    def test_wrong_password_and_parallel_attempts_are_limited(self):
        self.client.open(self.base).read()
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/auth/login',dict(password='incorrect-password'))
        self.assertEqual(e.exception.code,401)
        sid=self.sid()
        with ThreadPoolExecutor(max_workers=6) as pool:
            attempts=list(pool.map(lambda _:self.module.AUTH.login(sid,'incorrect-password','127.0.0.1')[1],range(6)))
        self.assertEqual(attempts.count(401),4);self.assertEqual(attempts.count(429),2)
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/auth/login',dict(password='test-password-only'))
        self.assertEqual(e.exception.code,429);self.assertEqual(e.exception.headers['Retry-After'],'300')
        with self.module.AUTH.lock:self.module.AUTH.failures['127.0.0.1']=(5,time.monotonic()-1)
        self.assertEqual(self.login().status,200)

    def test_expired_session_cannot_bypass_login(self):
        self.login().read();sid=self.sid()
        with self.module.AUTH.lock:self.module.AUTH.sessions[sid]=(True,time.monotonic()-1)
        with self.assertRaises(urllib.error.HTTPError) as e:self.client.open(self.base+'/api/projects')
        self.assertEqual(e.exception.code,401)

    def test_missing_short_password_fails_closed_and_secure_cookie_supported(self):
        with patch.dict(os.environ,ATELIER_PASSWORD_FILE=str(Path(self.temp.name)/'missing')):
            with self.assertRaises(ValueError):PasswordAuth.from_environment(self.password_file)
        with self.assertRaises(ValueError):PasswordAuth('short')
        with patch.dict(os.environ,ATELIER_PASSWORD_FILE=str(self.password_file),ATELIER_COOKIE_SECURE='true'):
            auth=PasswordAuth.from_environment(self.password_file)
        self.assertIn('; Secure',auth.cookie(auth.anonymous()))
        self.assertFalse(hasattr(auth,'password'))


if __name__=='__main__':unittest.main()
