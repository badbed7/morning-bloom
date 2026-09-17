"""Stable Windows bootstrap. Keeps its lock until the game exits."""
import argparse
import hashlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from release_config import REPOSITORY
from update_core import Installer, UpdateError, read_latest, manifest, download, version


def command(executable, runtime=None):
    return [str(runtime), '-I', str(executable)] if runtime else [str(executable)]


def python_runtime(executable, root, report):
    """Reuse dependencies by Python version and requirements hash, preserving older runtimes."""
    requirements = executable.parent.parent / 'python/requirements.txt'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    runtime = root / 'runtimes' / (f'{sys.version_info.major}.{sys.version_info.minor}-' + digest)
    python = runtime / 'Scripts/python.exe'
    ready = runtime / 'ready'
    if python.is_file() and ready.is_file():
        return python
    report('Python 실행 환경 준비 중… 첫 실행에는 시간이 걸릴 수 있습니다.')
    log_path = root / 'python-setup.log'
    with log_path.open('w', encoding='utf-8') as log:
        try:
            for args, timeout in (([sys.executable, '-I', '-m', 'venv', str(runtime)], 90),
                                  ([str(python), '-I', '-m', 'pip', 'install', '--disable-pip-version-check',
                                    '-r', str(requirements)], 600)):
                subprocess.run(args, timeout=timeout, check=True, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.SubprocessError) as exc:
            raise UpdateError('Python 실행 환경을 준비하지 못했습니다.\n' + str(log_path)) from exc
    ready.write_text(digest, encoding='ascii')
    return python


def health_check(executable, log_path, runtime=None):
    log_path = Path(log_path).resolve()
    system = sys.getwindowsversion() if sys.platform == 'win32' else sys.platform
    log_path.write_text(f'{system} / {64 if sys.maxsize > 2**32 else 32}-bit\nStartup check: {executable}\n', encoding='utf-8')
    with log_path.open('a', encoding='utf-8') as log:
        try:
            result = subprocess.run(command(executable, runtime) + ['--smoke-test', '--startup-log', str(log_path)],
                cwd=executable.parent, timeout=45, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode == 0: return True
            reason = f'Game startup exited with code {result.returncode} (0x{result.returncode & 0xffffffff:08X})'
        except subprocess.TimeoutExpired:
            reason = 'Game startup check timed out after 45 seconds'
        except OSError as exc:
            reason = f'Could not launch game: {exc}'
        log.write(reason + '\n')
    raise UpdateError(reason + '\nDiagnostic log: ' + str(log_path))


def acquire_lock(path):
    import msvcrt
    handle = path.open('a+b')
    handle.seek(0)
    if not handle.read(1): handle.write(b'0');handle.flush()
    handle.seek(0)
    try: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def prepare(installer, bundle, report):
    current = installer.current()
    errors, candidates = [], []
    def check(executable):
        runtime = python_runtime(executable, installer.root, report) if installer.python_mode else None
        return health_check(executable, installer.root / 'startup-check.log', runtime)

    # Query before unpacking anything; install only the newest usable candidate.
    try:
        report('GitHub 최신 버전 확인 중…')
        latest = read_latest(REPOSITORY, installer.python_mode)
        candidates.append((latest, None))
    except Exception as exc:
        errors.append(f'Update check: {exc}')
    bundled_name = 'bundled-python-update.json' if installer.python_mode else 'bundled-update.json'
    bundled_manifest = bundle / bundled_name
    if bundled_manifest.is_file():
        try:
            data = manifest(json.loads(bundled_manifest.read_text()), REPOSITORY, installer.python_mode)
            archive = bundle / ('MorningBloom-python.zip' if installer.python_mode else 'MorningBloom-game.zip')
            # Prefer an identical local payload; no repeated download is needed.
            candidates.insert(0, (data, archive))
        except Exception as exc:
            errors.append(f'Bundle: {exc}')
    for data, archive in sorted(candidates, key=lambda item: version(item[0]['version']), reverse=True):
        if current and version(data['version']) <= version(current['version']):
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='download-', dir=installer.root) as temp:
                if archive is None:
                    archive = Path(temp) / 'game.zip'
                    download(data, archive, report)
                report(f'v{data["version"]} 설치 및 실행 점검 중…')
                current = installer.install(archive, data, check)
            break
        except Exception as exc:
            errors.append(f'Install {data["version"]}: {exc}')
    try:
        (installer.root / 'update.log').write_text('\n'.join(errors) or 'Up to date', encoding='utf-8')
    except OSError:
        pass
    if current is None:
        raise UpdateError('실행할 버전을 준비하지 못했습니다. 인터넷과 배포 ZIP을 확인하세요.\n'
                          + str(installer.root / 'update.log') + '\n' + '\n'.join(errors))
    report(f'v{current["version"]} 시작 중…' + (' 업데이트 로그를 남겼습니다.' if errors else ''))
    return installer.executable(current)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', action='store_true', dest='python_mode')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--verify-bundle', action='store_true')
    args, game_args = parser.parse_known_args()
    if args.self_test:
        version('0.3.0')
        return 0
    bundle = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    if args.verify_bundle:
        log_path = bundle.parent / 'startup-check.log'
        try:
            with tempfile.TemporaryDirectory() as temp:
                installer = Installer(temp, args.python_mode)
                name = 'bundled-python-update.json' if args.python_mode else 'bundled-update.json'
                archive = 'MorningBloom-python.zip' if args.python_mode else 'MorningBloom-game.zip'
                data = manifest(json.loads((bundle / name).read_text()), REPOSITORY, args.python_mode)
                def check(executable):
                    try:
                        runtime = python_runtime(executable, installer.root,
                            lambda _: print('Preparing Python runtime...', flush=True)) if args.python_mode else None
                    except Exception:
                        setup_log = installer.root / 'python-setup.log'
                        if setup_log.is_file():
                            log_path.write_text(setup_log.read_text(encoding='utf-8', errors='replace'), encoding='utf-8')
                        raise
                    return health_check(executable, log_path, runtime)
                installer.install(bundle / archive, data, check)
        except Exception as exc:
            with log_path.open('a', encoding='utf-8') as log: log.write(str(exc) + '\n')
            return 1
        return 0
    root = tk.Tk()
    root.title('Morning Bloom')
    root.geometry('480x140')
    root.resizable(False, False)
    status = tk.StringVar(value='Morning Bloom 시작 중…')
    tk.Label(root, textvariable=status, padx=20, pady=35, wraplength=440).pack()
    root.protocol('WM_DELETE_WINDOW', lambda: None)
    local = Path(os.environ['LOCALAPPDATA'])
    installer = Installer(local / ('MorningBloomPythonLauncher' if args.python_mode else 'MorningBloomLauncher'), args.python_mode)
    lock_path = local / 'MorningBloomLauncher/launcher.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(lock_path)
    if lock is None:
        messagebox.showinfo('Morning Bloom', 'Morning Bloom이 이미 실행 중입니다.')
        root.destroy()
        return 0
    events = queue.Queue()
    def worker():
        try:
            exe = prepare(installer, bundle, lambda text: events.put(('status', text)))
            runtime = python_runtime(exe, installer.root, lambda text: events.put(('status', text))) if args.python_mode else None
            events.put(('ready', (command(exe, runtime) + game_args, exe.parent)))
        except Exception as exc: events.put(('error', str(exc)))
    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'status': status.set(value)
                elif kind == 'error':
                    messagebox.showerror('Morning Bloom', '시작하지 못했습니다.\n' + value)
                    root.destroy()
                    return
                elif kind == 'ready':
                    try:
                        process = subprocess.Popen(value[0], cwd=str(value[1]),
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    except OSError as exc:
                        messagebox.showerror('Morning Bloom', str(exc));root.destroy();return
                    root.withdraw()
                    def wait_game():
                        if process.poll() is None: root.after(500, wait_game)
                        else:
                            if process.returncode:
                                messagebox.showerror('Morning Bloom', f'게임이 종료되었습니다. 종료 코드: {process.returncode}')
                            root.destroy()
                    wait_game()
                    return
        except queue.Empty: pass
        root.after(100, poll)
    threading.Thread(target=worker, daemon=True).start()
    root.after(100, poll)
    root.mainloop()
    lock.close()
    return 0

if __name__ == '__main__': raise SystemExit(main())
