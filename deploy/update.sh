#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Keep the existing password, data volume, network binding and allowed hosts.
python3 - <<'PY'
from pathlib import Path
import re

compose = Path('compose.yaml')
source = compose.read_text(encoding='utf-8')
callback = re.compile(r'^\s*-\s*["\'](?:127\.0\.0\.1:)?1455:1455["\']\s*$')
updated = ''.join(line for line in source.splitlines(keepends=True) if not callback.match(line))
if source != updated:
    compose.with_name('compose.yaml.before-ai-removal').write_text(source, encoding='utf-8')
    compose.write_text(updated, encoding='utf-8')
for filename in ('app/chatgpt.py', 'app/analysis.py', 'app/handoff.py', 'tests/test_ai.py'):
    Path(filename).unlink(missing_ok=True)
PY

docker compose up -d --build
docker compose ps
