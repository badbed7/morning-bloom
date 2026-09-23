"""Build native Windows executables and complete offline bootstrap ZIP."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from build_icons import generate_icons

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
    repo = os.environ.get('BLOOM_RELEASE_REPO') or 'badbed7/morning-bloom'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo): raise SystemExit('Invalid repository')
    (ROOT / 'release/release_config.py').write_text(f'REPOSITORY = {repo!r}\n')
    icon = generate_icons(ROOT / 'assets/icons')
    common = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--distpath', 'dist', '--workpath', 'build', '--specpath', 'build', '--icon', str(icon)]
    google_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '').strip()
    google_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
    if google_id and not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', google_id):
        raise SystemExit('Invalid GOOGLE_OAUTH_CLIENT_ID')
    if bool(google_id) != bool(google_secret):
        raise SystemExit('GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set together')
    with tempfile.TemporaryDirectory(prefix='MorningBloom-build-config-') as config_dir:
        google_args = []
        if google_id:
            config = Path(config_dir) / 'google-oauth-client-id.txt'
            config.write_text(google_id, encoding='utf-8')
            secret = Path(config_dir) / 'google-oauth-client-secret.txt'
            secret.write_text(google_secret, encoding='utf-8')
            google_args = ['--add-data', str(config) + ';.', '--add-data', str(secret) + ';.']
        run(*common, '--onedir', '--name', 'MorningBloomGame', '--paths', 'python',
            '--add-data', str(ROOT / 'assets/fonts') + ';assets/fonts', *google_args,
            'release/game_entry.py')
    run(*common, '--onefile', '--name', 'MorningBloom', '--paths', 'release',
        '--add-data', str(icon) + ';assets/icons', 'release/launcher.py')
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
    (bootstrap / 'run.bat').write_text('@echo off\r\nstart "" /wait "%~dp0MorningBloom.exe" %*\r\n', encoding='ascii')
    (bootstrap / 'READ-ME.txt').write_text(
        'Extract this entire ZIP, then run MorningBloom.exe. No Python installation needed.\n'
        'Keep MorningBloom-game.zip and bundled-update.json beside the launcher for first launch.\n'
        'Game saves are kept separately in LocalAppData/MorningBloomPython.\n'
        'Updates are checked on launch. Offline mode uses the installed game.\n'
        'Update feed: https://github.com/' + repo + '/releases\n'
        'This prototype uses HTTPS and SHA-256 integrity checks; executables are not Authenticode signed.\n', encoding='utf-8')
    # Verify the packaged launcher without the build machine's Python/Qt paths.
    clean_env = {key: value for key, value in os.environ.items()
                 if not key.upper().startswith(('PYTHON', 'QT_', 'QML_', 'VIRTUAL_ENV'))}
    clean_env['PATH'] = os.environ['SystemRoot'] + '\\System32;' + os.environ['SystemRoot']
    with tempfile.TemporaryDirectory(prefix='MorningBloom-실행 점검-') as temp:
        result = subprocess.run([str(bootstrap / 'MorningBloom.exe'), '--verify-bundle'],
            cwd=temp, env=clean_env, stdin=subprocess.DEVNULL, timeout=90)
    if result.returncode:
        log = ROOT / 'build/startup-check.log'
        if log.exists(): print(log.read_text(encoding='utf-8', errors='replace'), flush=True)
        raise SystemExit('Packaged launcher startup check failed')
    zip_folder(bootstrap, output / f'MorningBloom-{release_version}-Windows-x64.zip')
    (output / 'release-notes.md').write_text(
        f'Morning Bloom {release_version}\n\n'
        '## 버그 수정\n\n'
        '- Google Drive 저장을 복원한 뒤 5분 자동 백업 확인 때 같은 저장을 새 변경으로 잘못 판단하여 "클라우드 저장 복원" 창이 반복되던 문제를 수정했습니다.\n'
        '- 다른 PC에서 실제로 변경한 저장은 계속 확인합니다. 기존 정원 저장 형식과 데이터는 유지됩니다.\n\n'
        '## 다운로드\n\n'
        f'- Python 실행: `MorningBloom-{release_version}-Python-BAT.zip` 전체 압축 해제 후 `run-python.bat` 실행. Python 3.12 64비트가 필요합니다.\n'
        f'- EXE 실행: `MorningBloom-{release_version}-Windows-x64.zip` 전체 압축 해제 후 `MorningBloom.exe` 실행. Python 설치가 필요 없습니다.\n'
        '- 기존 BAT·런처는 다음 실행 때 게임을 자동 업데이트합니다.\n\n'
        'Windows CI에서 게임·업데이터 테스트와 EXE·Python 묶음의 격리된 실행 검사를 통과했습니다.\n', encoding='utf-8')

if __name__ == '__main__': main()
