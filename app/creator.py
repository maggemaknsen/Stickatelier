"""Windows bridge setup packages and short-lived, single-use PNG handoffs."""
from io import BytesIO
from pathlib import Path
import json
import re
import secrets
import threading
import time
from zipfile import ZipFile, ZIP_DEFLATED


def setup_bundle(executable, origin):
    if not isinstance(executable, str):
        raise ValueError('Bitte den vollständigen Pfad zur Creator-EXE eingeben.')
    executable = executable.strip().strip('"')
    if not re.fullmatch(r'[A-Za-z]:\\[^"<>|?*\x00-\x1f]+\.exe', executable, re.IGNORECASE):
        raise ValueError('Ein lokaler Windows-Pfad zur EXE wird benötigt, ohne zusätzliche Startargumente.')
    if any(part in ('.', '..', '') for part in executable[3:].split('\\')):
        raise ValueError('Ungültiger Programmpfad.')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('config.json', json.dumps(dict(executable=executable, origin=origin), ensure_ascii=False))
        for source in sorted((Path(__file__).parent/'creator_bridge').iterdir()):
            text = source.read_text(encoding='utf-8')
            archive.writestr(source.name, ('\ufeff'+text if source.suffix == '.ps1' else text).encode('utf-8'))
    return output.getvalue()


class Handoffs:
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()

    def issue(self, path, session):
        now = time.monotonic()
        with self.lock:
            self.entries = {key: value for key, value in self.entries.items() if value[0] > now}
            if len(self.entries) >= 128:
                raise ValueError('Zu viele offene Übergaben. Bitte kurz warten.')
            token = secrets.token_hex(32)
            self.entries[token] = (now+120, path, session)
        return token

    def consume(self, token):
        if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{64}', token):
            return None
        with self.lock:
            value = self.entries.pop(token, None)
        return value if value and value[0] > time.monotonic() else None
