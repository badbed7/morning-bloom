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
        '## 새 콘텐츠\n\n'
        '- 레퍼런스 기반 장미·은방울꽃·토끼풀·해바라기·라벤더·물망초 추가, 데이지·튤립 외형 개선.\n'
        '- 주말용 팬지 2일·코스모스 3일·프리지아 4일, 휴가용 해바라기 5일·라벤더 7일·은방울꽃 14일.\n'
        '- 주말·휴가용 꽃은 첫 물주기 후 접속 없이 개화까지 성장합니다. 설정의 휴가 모드는 꺼 두세요.\n'
        '- 홀씨 바람놀이: 마우스·스페이스를 누르고 놓아 금빛 고리를 통과합니다. 꽃가루 5점당 1G, 입장료·대기시간 없이 반복합니다.\n'
        '- 데이지 꽃머리 앱 아이콘, 씨앗 봉투를 3개씩 넘기는 선택 화면.\n\n'
        '## 저장과 바탕화면\n\n'
        '- 재배 중인 화분도 바탕화면에 플로팅하며 성장 모습과 수확 후 위치를 유지합니다.\n'
        '- Google Drive 연결 시 실행 때 먼저 복원, 이후 5분마다 자동 업로드, 종료 전 마지막 업로드.\n'
        '- 기존 v1~v10 저장을 v11로 이전하고 씨앗·꽃·재화·꾸미기·플로팅 배치를 보존합니다. 이전 원문은 별도 백업합니다.\n'
        '- 여러 PC를 사용한다면 모두 최신 버전으로 업데이트하세요. v11 저장은 구버전에서 열 수 없습니다.\n\n'
        '## 다운로드\n\n'
        f'- Python 실행: `MorningBloom-{release_version}-Python-BAT.zip` 전체 압축 해제 후 `run-python.bat` 실행. Python 3.12 64비트가 필요합니다.\n'
        f'- EXE 실행: `MorningBloom-{release_version}-Windows-x64.zip` 전체 압축 해제 후 `MorningBloom.exe` 실행. Python 설치가 필요 없습니다.\n'
        '- 기존 BAT·런처는 다음 실행 때 게임을 자동 업데이트합니다. 새 런처 아이콘까지 적용하려면 새 배포 ZIP을 받으세요.\n'
        '- v0.6.0 이하 사용자는 새 배포 ZIP으로 런처를 한 번 교체해야 합니다.\n'
        '- 기존 정원 저장 위치는 그대로 유지합니다.\n\n'
        'Windows CI에서 게임·업데이터 테스트와 EXE·Python 묶음의 격리된 실행 검사를 통과했습니다.\n', encoding='utf-8')

if __name__ == '__main__': main()
