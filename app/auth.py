"""Shared-password access with expiring, server-side sessions."""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import threading
import time


class PasswordAuth:
    SESSION_SECONDS = 12 * 60 * 60
    LOGIN_SECONDS = 15 * 60
    RETRY_SECONDS = 5 * 60

    def __init__(self, password, secure=False):
        if not isinstance(password, str) or not 8 <= len(password) <= 256:
            raise ValueError('Das Atelier-Kennwort muss 8 bis 256 Zeichen enthalten.')
        self.salt = secrets.token_bytes(32)
        self.digest = self.hash(password)
        self.secure = secure
        self.sessions = {}
        self.failures = {}
        self.lock = threading.Lock()

    @classmethod
    def from_environment(cls, default_file):
        path = Path(os.environ.get('ATELIER_PASSWORD_FILE', str(default_file)))
        try:
            if path.stat().st_size > 1024:
                raise ValueError('Die Kennwortdatei ist zu groß.')
            password = path.read_text(encoding='utf-8').rstrip('\r\n')
        except OSError:
            raise ValueError('Kennwortdatei fehlt oder ist nicht lesbar. ATELIER_PASSWORD_FILE konfigurieren.') from None
        secure = os.environ.get('ATELIER_COOKIE_SECURE', 'false').lower()
        if secure not in ('true', 'false'):
            raise ValueError('ATELIER_COOKIE_SECURE muss true oder false sein.')
        return cls(password, secure == 'true')

    def hash(self, password):
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), self.salt, 600_000)

    def _prune(self, now):
        self.sessions = {sid: entry for sid, entry in self.sessions.items() if entry[1] > now}
        self.failures = {ip: entry for ip, entry in self.failures.items() if entry[1] > now}

    def valid(self, sid, authenticated=True):
        with self.lock:
            entry = self.sessions.get(sid)
            if not entry or entry[1] <= time.monotonic():
                self.sessions.pop(sid, None)
                return False
            return entry[0] or not authenticated

    def _issue(self, authenticated, now):
        self._prune(now)
        if len(self.sessions) >= 2048:
            self.sessions.pop(next(iter(self.sessions)))
        sid = secrets.token_urlsafe(32)
        self.sessions[sid] = (authenticated, now + (self.SESSION_SECONDS if authenticated else self.LOGIN_SECONDS))
        return sid

    def anonymous(self):
        with self.lock:
            return self._issue(False, time.monotonic())

    def login(self, sid, password, address):
        # Keep the rate check and password verification atomic, including parallel attempts.
        with self.lock:
            now = time.monotonic()
            self._prune(now)
            entry = self.sessions.get(sid)
            if not entry or entry[0]:
                return '', 403
            count, until = self.failures.get(address, (0, now + self.RETRY_SECONDS))
            if count >= 5 or (address not in self.failures and len(self.failures) >= 4096):
                return '', 429
            if not isinstance(password, str) or not 8 <= len(password) <= 256:
                matches = False
            else:
                matches = hmac.compare_digest(self.digest, self.hash(password))
            if not matches:
                self.failures[address] = (count + 1, until)
                return '', 401
            self.failures.pop(address, None)
            self.sessions.pop(sid, None)
            return self._issue(True, now), 200

    def logout(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def cookie(self, sid, authenticated=False):
        age = self.SESSION_SECONDS if authenticated else self.LOGIN_SECONDS
        if not sid:
            age = 0
        return f'atelier={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age={age}' + ('; Secure' if self.secure else '')
