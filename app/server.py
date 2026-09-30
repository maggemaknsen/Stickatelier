from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from io import BytesIO
from pathlib import Path
import base64
import hashlib
import html
import json
import os
import re
import threading
import urllib.parse
import uuid
import zipfile
from PIL import Image
from processing import decode, prepare, png, demo, settings, physical_width
from chatgpt import ChatGPT
from handoff import handoff_request, make_prompt
from auth import PasswordAuth

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('ATELIER_DATA', str(ROOT.parent/'data')))
DATA.mkdir(parents=True, exist_ok=True)
PROJECTS = DATA/'projects'
PROJECTS.mkdir(exist_ok=True)
AI = ChatGPT(DATA/'private')
WORKERS = threading.BoundedSemaphore(2)
AI_WORKER = threading.BoundedSemaphore(1)
HOSTS = set(os.environ.get('ATELIER_HOSTS','127.0.0.1,localhost').split(','))
AUTH = PasswordAuth.from_environment(ROOT.parent/'password.txt')

def project(identifier):
    if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{32}',identifier):
        raise ValueError('Ungültiges Projekt.')
    path = PROJECTS/identifier
    if not (path/'original.png').exists():
        raise ValueError('Projekt nicht gefunden. Bild erneut laden.')
    return path

def create(image, name, parent_id=None, kind=None):
    identifier = uuid.uuid4().hex
    directory = PROJECTS/identifier
    directory.mkdir()
    image.save(directory/'original.png')
    meta = dict(id=identifier, name=name[:120], width=image.width, height=image.height)
    if kind:
        meta['kind']=kind
    if parent_id:
        meta['parent_id']=parent_id
    (directory/'meta.json').write_text(json.dumps(meta),encoding='utf-8')
    return meta

class Handler(BaseHTTPRequestHandler):
    server_version = 'Stickatelier/0.1'
    def log_message(self, *_):
        # Do not log OAuth codes, credentials, filenames, or uploaded image data.
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
            if url.path == '/auth/callback':
                if self.server.server_port != 1455:
                    raise ValueError('Falscher Callback-Port.')
                if not self.session():
                    return self.send('Bitte zuerst im Stickatelier anmelden und die ChatGPT-Verbindung erneut starten.', 'text/plain; charset=utf-8', status=401)
                try:
                    AI.callback(args,self.session())
                    message = 'ChatGPT wurde verbunden. Du kannst dieses Fenster schließen und zum Stickatelier zurückkehren.'
                except ValueError as exc:
                    message = str(exc)
                return self.send('<!doctype html><html lang="de"><meta charset="utf-8"><title>Stickatelier – Anmeldung</title><p>'+html.escape(message)+'</p></html>', 'text/html; charset=utf-8')
            if self.server.server_port == 1455:
                return self.send(dict(error='Nicht gefunden.'),status=404)
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
            if url.path in ('/','/app.js','/color-tools.js'):
                name = 'index.html' if url.path == '/' else url.path[1:]
                mime = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','color-tools.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8','favicon.svg':'image/svg+xml'}[name]
                extra = {}
                return self.send((ROOT/'static'/name).read_bytes(),mime,extra=extra)
            if url.path == '/api/ai/status':
                return self.send(AI.status())
            if url.path == '/api/ai/models':
                return self.send(AI.models())
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
            if self.server.server_port == 1455 or not self.host_ok() or self.headers.get('X-Atelier') != '1':
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
                kind = self.headers.get('X-Atelier-Kind')
                parent_id = self.headers.get('X-Atelier-Source') or None
                if kind is not None and kind not in ('chatgpt-edit','chatgpt-generate'):
                    raise ValueError('Ungültige Motivvariante.')
                if parent_id:
                    if kind != 'chatgpt-edit':
                        raise ValueError('Ungültige Ausgangsvorlage.')
                    project(parent_id)
                if kind == 'chatgpt-edit' and not parent_id:
                    raise ValueError('Ausgangsvorlage fehlt. Bildbearbeitung erneut vorbereiten.')
                with WORKERS:
                    image = decode(self.body(20*1024*1024))
                    name = urllib.parse.unquote(self.headers.get('X-Filename','Motiv'))
                    return self.send(create(image,name,parent_id,kind))
            body = json.loads(self.body(16000))
            if not isinstance(body,dict):
                raise ValueError('Ungültige Anfrage.')
            if route == '/api/demo':
                return self.send(create(demo(),'Testmotiv · Farbflächen'))
            if route == '/api/ai/handoff':
                request = handoff_request(body)
                stats, image_data = None, None
                if request['action'] == 'edit':
                    directory = project(body.get('id'))
                    with WORKERS:
                        with Image.open(directory/'original.png') as original:
                            if request['image_source'] == 'prepared':
                                image, stats = prepare(original,request['settings'],max_edge=2048)
                                request['settings'] = stats['settings']
                            else:
                                image = original.copy()
                                image.thumbnail((2048,2048))
                                request['settings']['width_mm'] = physical_width(image,request['settings'])
                            image_data='data:image/png;base64,'+base64.b64encode(png(image,request['settings']['width_mm'])).decode()
                return self.send(dict(prompt=make_prompt(request,stats),image=image_data,
                                      action=request['action'],source_id=body.get('id') if request['action']=='edit' else None,
                                      settings=request['settings']))
            if route == '/api/ai/connect':
                return self.send(dict(url=AI.start(self.session())))
            if route == '/api/ai/disconnect':
                confirmed = AI.disconnect()
                return self.send(dict(message='Verbindung getrennt.' if confirmed else 'Lokal getrennt. Den Widerruf in den ChatGPT-Einstellungen prüfen.'))
            if route in ('/api/preview','/api/export','/api/ai/suggest'):
                directory = project(body.get('id'))
                s = settings(body.get('settings',{}))
                if route == '/api/ai/suggest':
                    if not AI_WORKER.acquire(blocking=False):
                        return self.send(dict(error='Eine KI-Anfrage läuft bereits.'),status=429)
                    try:
                        with Image.open(directory/'original.png') as original:
                            with WORKERS:
                                prepared, stats = prepare(original,s,max_edge=768)
                            original.thumbnail((768,768))
                            result = AI.suggest(png(original),str(body.get('model','')),stats['settings'],
                                                str(body.get('mode','logo'))[:30],str(body.get('goal',''))[:1000],png(prepared),stats)
                        return self.send(result)
                    finally:
                        AI_WORKER.release()
                with WORKERS:
                    with Image.open(directory/'original.png') as original:
                        image, stats = prepare(original,s,max_edge=1200 if route == '/api/preview' else 2400)
                    if route == '/api/preview':
                        return self.send(dict(image='data:image/png;base64,'+base64.b64encode(png(image)).decode(),stats=stats))
                    output = png(image,stats['width_mm'])
                    bio = BytesIO()
                    with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as package:
                        package.writestr('motiv-vorbereitet.png',output)
                        package.writestr('einstellungen.json',json.dumps(stats,ensure_ascii=False,indent=2))
                        palette = '\n'.join(f"{i+1}. {c['hex']} – {c['share']} %" for i,c in enumerate(stats['palette']))
                        instructions = (f"STICKATELIER – VORLAGE FÜR CREATOR 9\n\nZielgröße: {stats['width_mm']} × {stats['height_mm']} mm\n"
                            f"Farben: {stats['colors']}\n\n{palette}\n\nPNG in Creator 9 über Insert Artwork importieren. "
                            'Die oben genannte Größe in Creator ausdrücklich einstellen; die DPI-Angabe ist nur eine Hilfe. '
                            'Prepare Bitmap prüfen, dann Auto-Digitize oder Magic Wand verwenden. '
                            'Transparente Bereiche nicht als Stickfläche übernehmen. '
                            'Unterlagen, Stichdichte, Stichrichtung, Reihenfolge und Zugausgleich prüfen. '
                            'Als bearbeitbares Creator-Projekt speichern und erst danach das Maschinenformat exportieren. '
                            'Ein Probestick auf vergleichbarem Material bleibt erforderlich.\n\n'
                            'Diese Datei ist eine Grafikvorlage, keine Stickdatei. Farbanteile sind Pixelanteile, kein Garnverbrauch.\n')
                        package.writestr('creator-9-hinweise.txt',instructions)
                    # Persist this exported variant, without ever overwriting the source.
                    digest = hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()[:16]
                    (directory/f'export-{digest}.zip').write_bytes(bio.getvalue())
                    return self.send(bio.getvalue(),'application/zip',extra={'Content-Disposition':'attachment; filename="stickatelier-creator9.zip"'})
            return self.send(dict(error='Nicht gefunden.'),status=404)
        except (ValueError,TypeError,KeyError) as exc:
            self.send(dict(error=str(exc) if isinstance(exc,ValueError) else 'Ungültige Anfrage.'),status=400)
        except Exception:
            self.send(dict(error='Verarbeitung fehlgeschlagen. Bitte erneut versuchen.'),status=500)

if __name__ == '__main__':
    callback = ThreadingHTTPServer(('0.0.0.0',1455),Handler)
    threading.Thread(target=callback.serve_forever,daemon=True).start()
    port = int(os.environ.get('ATELIER_PORT','8080'))
    host = os.environ.get('ATELIER_BIND','0.0.0.0')
    print(f'Stickatelier bereit auf Port {port}.')
    ThreadingHTTPServer((host,port),Handler).serve_forever()
