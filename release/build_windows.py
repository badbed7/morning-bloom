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
            '--add-data', str(ROOT / 'assets/fonts') + ';assets/fonts',
            '--add-data', str(ROOT / 'assets/catalog') + ';assets/catalog', *google_args,
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
        '## 상점 꽃길 뽑기 진입 강조\n\n'
        '- 상점 맨 위의 초록색 강조 카드와 큰 버튼에서 60칸 보드를 바로 엽니다. 무료권과 1회/10회 비용을 함께 표시합니다.\n'
        '- 작은 창에서도 진입 버튼이 보이며 씨앗 구매는 스크롤로 이용할 수 있습니다.\n\n'
        '## 0.8.8 철회 대체 · 60칸 꽃길 보드와 프리뷰\n\n'
        '- 주사위 2개의 눈과 합을 표시하고 민들레 씨가 합만큼 칸을 따라 이동합니다. 60번 다음은 1번으로 이어지며 도착 칸에서만 보상을 받습니다.\n'
        '- 10회 연속 연출과 건너뛰기를 지원합니다. docs/gacha-board-preview.html도 같은 규칙으로 갱신했습니다.\n'
        '- 0.8.8 공개 배포는 철회했으며 이 버전이 대체합니다.\n'
        '## 자동 업데이트 조회와 구버전 실행 안내 수정\n\n'
        '- 조회 제한을 5초에서 15초로 늘리고 GitHub Release API와 버전별 고정 주소를 사용합니다. API 실패 시 기존 공개 주소로 재시도합니다.\n'
        '- 조회·설치 실패로 이전 버전을 실행하면 현재 버전과 진단 로그를 안내합니다.\n'
        '- 중요: 런처 자체는 게임 자동 업데이트로 바뀌지 않습니다. 이번 ZIP을 새 폴더에 전체 해제하고 그 폴더의 BAT 또는 런처로 한 번 실행하세요. 기존 바로가기는 새 폴더로 바꿔 주세요.\n'
        '- 기존 정원 저장은 유지합니다. 설치 폴더나 저장 폴더를 지울 필요가 없습니다.\n'
        '- 주사위 2개와 민들레 씨 보드 이동, 로즈 뽑기 전용, 교환잎 비료 구매를 포함합니다.\n\n'
        '## 다운로드\n\n'
        f'- Python 실행: `MorningBloom-{release_version}-Python-BAT.zip` 전체 압축 해제 후 `run-python.bat` 실행. Python 3.12 64비트가 필요합니다.\n'
        f'- EXE 실행: `MorningBloom-{release_version}-Windows-x64.zip` 전체 압축 해제 후 `MorningBloom.exe` 실행. Python 설치가 필요 없습니다.\n'
        '- 기존 BAT·런처는 다음 실행 때 게임을 자동 업데이트합니다.\n\n'
        'Windows CI에서 게임·업데이터 테스트와 EXE·Python 묶음의 격리된 실행 검사를 통과했습니다.\n', encoding='utf-8')

if __name__ == '__main__': main()


