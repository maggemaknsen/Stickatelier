from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    def test_update_preserves_hosts_password_and_projects_and_is_repeatable(self):
        script = (ROOT/'deploy/update.sh').read_text(encoding='utf-8')
        migration = script.split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            compose = (ROOT/'compose.yaml').read_text(encoding='utf-8')
            compose = compose.replace('      - "127.0.0.1:8080:8080"',
                '      - "8080:8080"\n      - "127.0.0.1:1455:1455"')
            compose = compose.replace('    environment:',
                '    environment:\n      ATELIER_HOSTS: "192.168.13.233,stickatelier.brassbound.de"')
            (directory/'compose.yaml').write_text(compose, encoding='utf-8')
            password = directory/'password.txt'
            password.write_text('test-only-password', encoding='utf-8')
            project = directory/'data/projects/existing/original.png'
            project.parent.mkdir(parents=True)
            project.write_bytes(b'preserved-original')
            obsolete = ('app/chatgpt.py','app/analysis.py','app/handoff.py','tests/test_ai.py')
            for name in obsolete:
                path = directory/name
                path.parent.mkdir(exist_ok=True)
                path.write_text('old module', encoding='utf-8')
            for _ in range(2):
                subprocess.run([sys.executable, '-c', migration], cwd=directory, check=True)
                expected = compose.replace('      - "127.0.0.1:1455:1455"\n', '')
                self.assertEqual((directory/'compose.yaml').read_text(encoding='utf-8'), expected)
                self.assertEqual((directory/'compose.yaml.before-ai-removal').read_text(encoding='utf-8'), compose)
                self.assertEqual(password.read_text(encoding='utf-8'), 'test-only-password')
                self.assertEqual(project.read_bytes(), b'preserved-original')
                self.assertTrue(all(not (directory/name).exists() for name in obsolete))


if __name__ == '__main__':
    unittest.main()
