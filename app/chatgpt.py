"""Optional official SIWC provider. No API-key billing or image-generation calls."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.parse
import urllib.request
import urllib.error

AUTH = 'https://auth.openai.com'
API = 'https://api.openai.com/v1'
CALLBACK = 'http://127.0.0.1:1455/auth/callback'

def remote(url, payload=None, token=None, form=False):
    body = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        body = (urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'OpenAI-Anfrage abgelehnt (HTTP {exc.code}). Anmeldung und Kontingent prüfen.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('OpenAI ist derzeit nicht erreichbar. Manuelle Bearbeitung bleibt verfügbar.') from None

class ChatGPT:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = self.directory / 'connection.json'
        self.lock = threading.RLock()
        self.pending = {}
        host = self.directory / 'host.json'
        if not host.exists():
            self.save(host, {'id': 'urn:uuid:' + __import__('uuid').uuid4().hex})
        self.host_id = json.loads(host.read_text())['id']
        self.profile = json.loads(self.file.read_text()) if self.file.exists() else {}

    def save(self, path, obj):
        tmp = path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f)
        os.replace(tmp, path)

    def status(self):
        with self.lock:
            return dict(connected=bool(self.profile.get('access_token')),
                        email=self.profile.get('email',''),
                        plan_enabled='chatgpt.tokens.use.direct' in self.profile.get('scopes',[]))

    def start(self, browser_session):
        with self.lock:
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            self.pending = {k:v for k,v in self.pending.items() if v['expires'] > time.time()}
            old = self.profile
            p = dict(state=state, nonce=nonce, verifier=verifier, session=browser_session,
                     expires=time.time()+600, client_id=old.get('client_id'), subject=old.get('sub'))
            self.pending[state] = p
            query = dict(client_id=p['client_id'] or 'dynamic_agent_client', ext_agent_host_id=self.host_id,
                         response_type='code', redirect_uri=CALLBACK, nonce=nonce, state=state,
                         scope='openid profile email offline_access resource.invoke chatgpt.tokens.use.direct',
                         resource=API, code_challenge_method='S256',
                         code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
            if not p['client_id']:
                query['agent_name_hint'] = 'Stickatelier'
            elif old.get('id_token'):
                query['id_token_hint'] = old['id_token']
            return AUTH+'/api/accounts/authorize?'+urllib.parse.urlencode(query)

    def callback(self, query, browser_session):
        with self.lock:
            state = query.get('state', [''])[0]
            p = self.pending.pop(state, None)
            if not p or p['expires'] < time.time() or not secrets.compare_digest(p['session'], browser_session):
                raise ValueError('Die Anmeldung ist abgelaufen oder gehört zu einem anderen Browser. Neu starten.')
            if query.get('error'):
                raise ValueError('Die ChatGPT-Anmeldung wurde nicht abgeschlossen.')
            issued = query.get('client_id',[p['client_id']])[0]
            if not issued or issued == 'dynamic_agent_client' or (p['client_id'] and issued != p['client_id']):
                raise ValueError('Ungültige App-Registrierung.')
            code = query.get('code',[''])[0]
            if not code:
                raise ValueError('OpenAI hat keinen Anmeldecode geliefert.')
            token = remote(AUTH+'/api/accounts/oauth/token', dict(grant_type='authorization_code',
                client_id=issued, code=code, code_verifier=p['verifier'], redirect_uri=CALLBACK, resource=API), form=True)
            try:
                import jwt
                client = jwt.PyJWKClient(AUTH+'/.well-known/jwks.json')
                identity = jwt.decode(token['id_token'], client.get_signing_key_from_jwt(token['id_token']).key,
                                      algorithms=['RS256','ES256'], audience=issued, issuer=AUTH,
                                      leeway=5, options={'require':['sub','exp','iat','nonce']})
                if identity['nonce'] != p['nonce'] or (p['subject'] and identity['sub'] != p['subject']):
                    raise ValueError('Die bestätigte Identität passt nicht zur Anmeldung.')
            except ImportError:
                raise ValueError('Für die Anmeldung fehlt PyJWT. Docker-Image neu bauen.') from None
            except Exception:
                raise ValueError('Die OpenAI-Identität konnte nicht sicher bestätigt werden.') from None
            self.profile = dict(client_id=issued, sub=identity['sub'], email=identity.get('email',''),
                                scopes=token.get('scope','').split(), access_token=token.get('access_token'),
                                refresh_token=token.get('refresh_token'), id_token=token['id_token'],
                                expires=time.time()+int(token.get('expires_in',3600)))
            self.save(self.file,self.profile)

    def access(self):
        with self.lock:
            p = self.profile
            if not p.get('access_token') or 'chatgpt.tokens.use.direct' not in p.get('scopes',[]):
                raise ValueError('Zuerst ChatGPT verbinden und die Nutzung des Tarifkontingents erlauben.')
            if p.get('expires',0) <= time.time()+60:
                if not p.get('refresh_token'):
                    raise ValueError('ChatGPT bitte erneut verbinden.')
                token = remote(AUTH+'/api/accounts/oauth/token', dict(grant_type='refresh_token',
                    client_id=p['client_id'], refresh_token=p['refresh_token'], resource=API), form=True)
                p.update(access_token=token['access_token'], refresh_token=token.get('refresh_token',p['refresh_token']),
                         expires=time.time()+int(token.get('expires_in',3600)))
                if 'scope' in token:
                    p['scopes'] = token['scope'].split()
                if 'chatgpt.tokens.use.direct' not in p['scopes']:
                    raise ValueError('Die Freigabe zur Tarifnutzung fehlt. Erneut anmelden.')
                self.save(self.file,p)
            return p['access_token']

    def models(self):
        result = remote(API+'/models',token=self.access())
        return [dict(id=m['slug'], name=m.get('display_name',m['slug']))
                for m in result.get('models',[]) if m.get('visibility') == 'list']

    def disconnect(self):
        with self.lock:
            confirmed = False
            p = self.profile
            if p.get('refresh_token'):
                try:
                    discovery = remote(AUTH+'/.well-known/openid-configuration')
                    endpoint = discovery['revocation_endpoint']
                    if not endpoint.startswith(AUTH+'/'):
                        raise ValueError('Unerwarteter Widerrufsendpunkt.')
                    data = urllib.parse.urlencode(dict(token=p['refresh_token'],token_type_hint='refresh_token',client_id=p['client_id'])).encode()
                    with urllib.request.urlopen(urllib.request.Request(endpoint,data,{'Content-Type':'application/x-www-form-urlencoded'}),timeout=20) as r:
                        confirmed = r.status == 200
                except Exception:
                    pass
            for key in ('access_token','refresh_token','id_token','expires'):
                p.pop(key,None)
            self.pending.clear()
            self.save(self.file,p)
            return confirmed

    def suggest(self, image_bytes, selected, current, mode, goal, prepared_bytes=None, stats=None):
        from analysis import INSTRUCTIONS, parse_analysis
        catalog = self.models()
        if selected not in [m['id'] for m in catalog]:
            raise ValueError('Bitte ein verfügbares Modell auswählen.')
        content = [dict(type='input_text',text=json.dumps(dict(mode=mode,goal=goal,settings=current,stats=stats,first_image='Original',second_image='Vorbereitetes Motiv'),ensure_ascii=False)),
                   dict(type='input_image',image_url='data:image/png;base64,'+base64.b64encode(image_bytes).decode())]
        if prepared_bytes:
            content.append(dict(type='input_image',image_url='data:image/png;base64,'+base64.b64encode(prepared_bytes).decode()))
        payload = dict(model=selected, store=False, stream=True, instructions=INSTRUCTIONS, input=[dict(role='user',content=content)])
        request = urllib.request.Request(API+'/responses',json.dumps(payload).encode(),
            {'Content-Type':'application/json','Accept':'text/event-stream','Authorization':'Bearer '+self.access()})
        output, completed = '', False
        try:
            with urllib.request.urlopen(request,timeout=120) as response:
                for line in response:
                    if not line.startswith(b'data: '):
                        continue
                    raw = line[6:].strip()
                    if raw == b'[DONE]':
                        continue
                    event = json.loads(raw)
                    kind = event.get('type')
                    if kind == 'response.output_text.delta':
                        output += event.get('delta','')
                        if len(output) > 30_000:
                            raise ValueError('Die KI-Antwort ist zu lang.')
                    elif kind == 'response.completed':
                        completed = True
                    elif kind in ('response.failed','response.incomplete','error'):
                        raise ValueError('KI-Anfrage nicht abgeschlossen. Kontingent und Verbindung prüfen.')
        except urllib.error.HTTPError as exc:
            raise ValueError(f'KI-Anfrage abgelehnt (HTTP {exc.code}). Kontingent oder Modell prüfen.') from None
        except (urllib.error.URLError,TimeoutError):
            raise ValueError('KI-Verbindung unterbrochen. Manuell weiterarbeiten oder erneut versuchen.') from None
        if not completed:
            raise ValueError('Die KI-Anfrage wurde nicht vollständig abgeschlossen.')
        return parse_analysis(output,current)
