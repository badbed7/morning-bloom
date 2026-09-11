"""Build native Windows executables and complete offline bootstrap ZIP."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(*args): subprocess.run([str(a) for a in args], cwd=ROOT, check=True)

def zip_folder(source, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file(): archive.write(path, path.relative_to(source).as_posix())

def main():
    if sys.platform != 'win32': raise SystemExit('Build on Windows x64 with Python 3.12')
    release_version = (ROOT / 'release/VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', release_version): raise SystemExit('Invalid version')
    repo = os.environ.get('BLOOM_RELEASE_REPO') or 'badbed7/morning-bloom-releases'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo): raise SystemExit('Invalid repository')
    (ROOT / 'release/release_config.py').write_text(f'REPOSITORY = {repo!r}\n')
    common = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--distpath', 'dist', '--workpath', 'build', '--specpath', 'build']
    run(*common, '--onedir', '--name', 'MorningBloomGame', '--paths', 'python',
        '--add-data', 'assets/fonts:assets/fonts', 'release/game_entry.py')
    run(*common, '--onefile', '--name', 'MorningBloom', '--paths', 'release', 'release/launcher.py')
    game = ROOT / 'dist/MorningBloomGame'
    licenses = game / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy(ROOT / 'assets/fonts/OFL.txt', licenses / 'Noto-OFL.txt')
    # Include upstream license texts shipped with the runtime dependencies.
    import importlib.metadata
    for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'PyInstaller'):
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if 'license' in str(file).lower() or 'copying' in str(file).lower():
                path = Path(distribution.locate_file(file))
                if path.is_file():
                    destination = licenses / package / Path(str(file)).name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(path, destination)
    run(game / 'MorningBloomGame.exe', '--smoke-test')
    run(ROOT / 'dist/MorningBloom.exe', '--self-test')
    output = ROOT / 'release-output'
    output.mkdir(exist_ok=True)
    payload = output / 'MorningBloom-game.zip'
    zip_folder(game, payload)
    data = dict(protocol=1, version=release_version, size=payload.stat().st_size,
        sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),
        url=f'https://github.com/{repo}/releases/download/v{release_version}/MorningBloom-game.zip')
    (output / 'update.json').write_text(json.dumps(data, indent=2))
    bootstrap = ROOT / 'build/bootstrap'
    bootstrap.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / 'dist/MorningBloom.exe', bootstrap)
    shutil.copy(payload, bootstrap)
    shutil.copy(output / 'update.json', bootstrap / 'bundled-update.json')
    (bootstrap / 'READ-ME.txt').write_text(
        'Extract this entire ZIP, then run MorningBloom.exe. No Python installation needed.\n'
        'Keep MorningBloom-game.zip and bundled-update.json beside the launcher for first launch.\n'
        'Game saves are kept separately in LocalAppData/MorningBloomPython.\n'
        'Updates are checked on launch. Offline mode uses the installed game.\n'
        'Update feed: https://github.com/' + repo + '/releases\n'
        'This prototype uses HTTPS and SHA-256 integrity checks; executables are not Authenticode signed.\n', encoding='utf-8')
    zip_folder(bootstrap, output / f'MorningBloom-{release_version}-Windows-x64.zip')
    (output / 'release-notes.md').write_text(
        f'Morning Bloom {release_version}\n\nDownload the Windows-x64 ZIP, extract all files and run MorningBloom.exe.\n'
        'Includes Python and Qt. Automatic game updates are checked on launch.\n'
        'If the public distribution feed is not connected yet, this package works offline and updates will be unavailable.\n'
        'Unsigned prototype; native executable startup and isolated game smoke test passed in Windows CI.\n', encoding='utf-8')

if __name__ == '__main__': main()
