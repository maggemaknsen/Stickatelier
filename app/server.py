from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import threading
import urllib.parse
import uuid
from PIL import Image
from processing import decode, prepare, png, demo, settings
from auth import PasswordAuth
from creator import Handoffs, setup_bundle

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('ATELIER_DATA', str(ROOT.parent/'data')))
DATA.mkdir(parents=True, exist_ok=True)
PROJECTS = DATA/'projects'
PROJECTS.mkdir(exist_ok=True)
WORKERS = threading.BoundedSemaphore(2)
HOSTS = set(os.environ.get('ATELIER_HOSTS','127.0.0.1,localhost').split(','))
AUTH = PasswordAuth.from_environment(ROOT.parent/'password.txt')
CREATOR_HANDOFFS = Handoffs()

def project(identifier):
    if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{32}',identifier):
        raise ValueError('Ungültiges Projekt.')
    path = PROJECTS/identifier
    if not (path/'original.png').exists():
        raise ValueError('Projekt nicht gefunden. Bild erneut laden.')
    return path

def create(image, name):
    identifier = uuid.uuid4().hex
    directory = PROJECTS/identifier
    directory.mkdir()
    image.save(directory/'original.png')
    meta = dict(id=identifier, name=name[:120], width=image.width, height=image.height)
    (directory/'meta.json').write_text(json.dumps(meta),encoding='utf-8')
    return meta

class Handler(BaseHTTPRequestHandler):
    server_version = 'Stickatelier/0.1'
    def log_message(self, *_):
        # Do not log credentials, filenames, or uploaded image data.
        pass
    def send(self, data, mime='application/json; charset=utf-8', status=200, extra=None):
        if isinstance(data,dict) or isinstance(data,list):
            data = json.dumps(data,ensure_ascii=False).encode()
        elif isinstance(data,str):
            data = data.encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (extra or {}).items():
            self.send_header(k,v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):
            pass
    def session(self, authenticated=True):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie',''))
            sid = cookie['atelier'].value if 'atelier' in cookie else ''
            return sid if AUTH.valid(sid, authenticated) else ''
        except Exception:
            return ''
    def host_ok(self):
        raw = self.headers.get('Host','')
        return raw.split(':')[0] in HOSTS
    def body(self,limit):
        n = int(self.headers.get('Content-Length','0'))
        if not 0 < n <= limit:
            raise ValueError('Datei oder Anfrage ist zu groß beziehungsweise leer.')
        self.connection.settimeout(30)
        data = self.rfile.read(n)
        if len(data) != n:
            raise ValueError('Upload wurde nicht vollständig übertragen.')
        return data
    def do_GET(self):
        try:
            if not self.host_ok():
                return self.send(dict(error='Nicht erlaubter Host.'),status=403)
            url = urllib.parse.urlsplit(self.path)
            args = urllib.parse.parse_qs(url.query)
            if url.path == '/api/health':
                return self.send(dict(ok=True))
            if url.path == '/api/creator-file':
                handoff = CREATOR_HANDOFFS.consume(args.get('token', [''])[0])
                if not handoff or not AUTH.valid(handoff[2], True):
                    return self.send(dict(error='Übergabe abgelaufen oder bereits verwendet. Bitte erneut in Creator öffnen.'),status=410)
                return self.send(handoff[1].read_bytes(), 'image/png', extra={'Content-Disposition':'attachment; filename="stickatelier-motiv.png"'})
            if url.path in ('/style.css','/login.js','/favicon.svg') or (url.path in ('/','/login') and not self.session()):
                login = url.path in ('/','/login')
                name = 'login.html' if login else url.path[1:]
                mime = {'login.html':'text/html; charset=utf-8','login.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8','favicon.svg':'image/svg+xml'}[name]
                extra = {}
                if login and not self.session(False):
                    extra['Set-Cookie'] = AUTH.cookie(AUTH.anonymous())
                return self.send((ROOT/'static'/name).read_bytes(),mime,extra=extra)
            if not self.session():
                return self.send(dict(error='Bitte im Stickatelier anmelden.'),status=401)
            if url.path == '/login':
                return self.send('',status=303,extra={'Location':'/'})
            if url.path in ('/','/app.js','/color-tools.js','/fill-cursor.svg','/fill-preview-worker.js'):
                name = 'index.html' if url.path == '/' else url.path[1:]
                mime = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','color-tools.js':'text/javascript; charset=utf-8','fill-preview-worker.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8','favicon.svg':'image/svg+xml','fill-cursor.svg':'image/svg+xml'}[name]
                extra = {}
                return self.send((ROOT/'static'/name).read_bytes(),mime,extra=extra)
            if url.path == '/api/projects':
                entries = sorted(PROJECTS.glob('*/meta.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]
                return self.send([json.loads(p.read_text(encoding='utf-8')) for p in entries])
            if url.path == '/api/original':
                directory = project(args.get('id',[''])[0])
                return self.send((directory/'original.png').read_bytes(),'image/png')
            if url.path == '/api/project':
                directory = project(args.get('id',[''])[0])
                return self.send(json.loads((directory/'meta.json').read_text(encoding='utf-8')))
            return self.send(dict(error='Nicht gefunden.'),status=404)
        except ValueError as exc:
            self.send(dict(error=str(exc)),status=400)
        except Exception:
            self.send(dict(error='Die Anfrage konnte nicht verarbeitet werden.'),status=500)
    def do_POST(self):
        try:
            if not self.host_ok() or self.headers.get('X-Atelier') != '1':
                return self.send(dict(error='Anfrage nicht erlaubt.'),status=403)
            origin = self.headers.get('Origin')
            if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get('Host'):
                return self.send(dict(error='Anfrage nicht erlaubt.'),status=403)
            route = urllib.parse.urlsplit(self.path).path
            if route == '/auth/login':
                sid = self.session(False)
                if not sid:
                    return self.send(dict(error='Anmeldeseite neu laden und erneut versuchen.'),status=403)
                if self.session():
                    return self.send(dict(ok=True))
                body = json.loads(self.body(2048))
                if not isinstance(body,dict):
                    raise ValueError('Ungültige Anfrage.')
                sid, status = AUTH.login(sid,body.get('password'),self.client_address[0])
                if status != 200:
                    message = 'Zu viele Versuche. Bitte in fünf Minuten erneut versuchen.' if status == 429 else 'Kennwort stimmt nicht.'
                    return self.send(dict(error=message),status=status,extra={'Retry-After':'300'} if status == 429 else None)
                return self.send(dict(ok=True),extra={'Set-Cookie':AUTH.cookie(sid,True)})
            if not self.session():
                return self.send(dict(error='Bitte im Stickatelier anmelden.'),status=401)
            if route == '/auth/logout':
                AUTH.logout(self.session())
                return self.send(dict(ok=True),extra={'Set-Cookie':AUTH.cookie('')})
            if route == '/api/upload':
                with WORKERS:
                    image = decode(self.body(20*1024*1024))
                    name = urllib.parse.unquote(self.headers.get('X-Filename','Motiv'))
                    return self.send(create(image,name))
            # Authenticated editing requests include bounded brush point lists.
            body = json.loads(self.body(1024*1024))
            if not isinstance(body,dict):
                raise ValueError('Ungültige Anfrage.')
            if route == '/api/demo':
                return self.send(create(demo(),'Testmotiv · Farbflächen'))
            if route == '/api/creator-setup':
                source = urllib.parse.urlsplit(body.get('origin', ''))
                if source.scheme not in ('http', 'https') or source.hostname not in HOSTS or source.netloc != self.headers.get('Host') or source.path or source.query or source.fragment or source.username:
                    raise ValueError('Ungültige Stickatelier-Adresse.')
                output = setup_bundle(body.get('executable'), f'{source.scheme}://{source.netloc}')
                return self.send(output, 'application/zip', extra={'Content-Disposition':'attachment; filename="stickatelier-creator-einrichtung.zip"'})
            if route in ('/api/preview','/api/export','/api/creator-export'):
                directory = project(body.get('id'))
                s = settings(body.get('settings',{}))
                with WORKERS:
                    with Image.open(directory/'original.png') as original:
                        image, stats = prepare(original,s,max_edge=2400)
                    if route == '/api/preview':
                        return self.send(dict(image='data:image/png;base64,'+base64.b64encode(png(image)).decode(),stats=stats))
                    output = png(image,stats['width_mm'])
                    digest = hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()[:16]
                    exported = directory/f'export-{digest}.png'
                    temporary = directory/f'.export-{uuid.uuid4().hex}.png'
                    temporary.write_bytes(output)
                    temporary.replace(exported)
                    if route == '/api/creator-export':
                        token = CREATOR_HANDOFFS.issue(exported, self.session())
                        return self.send(dict(path='/api/creator-file?token='+token))
                    return self.send(output,'image/png',extra={'Content-Disposition':'attachment; filename="stickatelier-motiv.png"'})
            return self.send(dict(error='Nicht gefunden.'),status=404)
        except (ValueError,TypeError,KeyError) as exc:
            self.send(dict(error=str(exc) if isinstance(exc,ValueError) else 'Ungültige Anfrage.'),status=400)
        except Exception:
            self.send(dict(error='Verarbeitung fehlgeschlagen. Bitte erneut versuchen.'),status=500)

if __name__ == '__main__':
    port = int(os.environ.get('ATELIER_PORT','8080'))
    host = os.environ.get('ATELIER_BIND','0.0.0.0')
    print(f'Stickatelier bereit auf Port {port}.')
    ThreadingHTTPServer((host,port),Handler).serve_forever()
