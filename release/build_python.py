"""Package the Python game and stable BAT launcher using an explicit file allowlist."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_windows import ROOT, zip_folder
from build_icons import generate_icons
from update_core import manifest


def main():
    version = (ROOT / 'release/VERSION').read_text(encoding='utf-8').strip()
    repository = os.environ.get('BLOOM_RELEASE_REPO', 'badbed7/morning-bloom')
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '').strip()
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
    if client_id and not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', client_id):
        raise SystemExit('Invalid GOOGLE_OAUTH_CLIENT_ID')
    if bool(client_id) != bool(client_secret):
        raise SystemExit('GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set together')
    output = ROOT / 'release-output'
    output.mkdir(exist_ok=True)
    icon = generate_icons(ROOT / 'assets/icons')
    with tempfile.TemporaryDirectory(prefix='MorningBloom-python-build-') as temp:
        stage = Path(temp) / 'game'
        paths = list((ROOT / 'python/morning_bloom').rglob('*.py'))
        paths += [ROOT / name for name in ('python/requirements.txt', 'release/game_entry.py',
                  'assets/fonts/NotoSansKR-Subset.otf', 'assets/fonts/OFL.txt')]
        for source in paths:
            target = stage / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if client_id:
            (stage / 'python/google-oauth-client-id.txt').write_text(client_id, encoding='utf-8')
            (stage / 'python/google-oauth-client-secret.txt').write_text(client_secret, encoding='utf-8')
        payload = output / 'MorningBloom-python.zip'
        zip_folder(stage, payload)
        data = manifest(dict(protocol=1, version=version, size=payload.stat().st_size,
            sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),
            url=f'https://github.com/{repository}/releases/download/v{version}/{payload.name}'), repository, True)
        (output / 'python-update.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        bootstrap = Path(temp) / 'bootstrap'
        (bootstrap / 'release').mkdir(parents=True)
        (bootstrap / 'assets/icons').mkdir(parents=True)
        shutil.copyfile(icon, bootstrap / 'assets/icons/morning-bloom.ico')
        for name in ('run-python.bat', 'release/launcher.py', 'release/update_core.py', 'release/release_config.py'):
            shutil.copyfile(ROOT / name, bootstrap / name)
        (bootstrap / 'release/release_config.py').write_text(f'REPOSITORY = {repository!r}\n', encoding='utf-8')
        shutil.copyfile(payload, bootstrap / payload.name)
        (bootstrap / 'bundled-python-update.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        (bootstrap / 'READ-ME.txt').write_text(
            'Install Python 3.12 64-bit with Python Launcher and Tcl/Tk once.\n'
            'Extract all files, then run run-python.bat. Do not move the BAT alone.\n'
            'Each launch checks GitHub Releases, verifies and installs an update, then starts the Python game.\n'
            'Internet is required to install dependencies for the first time. Later offline launches use the installed version.\n'
            'Saved gardens: %LOCALAPPDATA%/MorningBloomPython (shared with the EXE version).\n'
            'Game installations and dependency runtimes: %LOCALAPPDATA%/MorningBloomPythonLauncher.\n', encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(bootstrap / 'release/launcher.py'), '--python', '--verify-bundle'])
        if result.returncode:
            log = Path(temp) / 'startup-check.log'
            if log.is_file():
                shutil.copyfile(log, output / 'python-startup-check.log')
                sys.stderr.buffer.write(log.read_bytes())
            raise SystemExit('Python BAT startup check failed; see release-output/python-startup-check.log')
        zip_folder(bootstrap, output / f'MorningBloom-{version}-Python-BAT.zip')
    print('Python BAT bundle verified and packaged.')


if __name__ == '__main__':
    main()
