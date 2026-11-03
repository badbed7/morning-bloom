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

# Isolated BAT diagnostics must still import this trusted, bundled release directory.
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_config import REPOSITORY
from update_core import Installer, UpdateError, read_latest, manifest, download, version
from live_update import Coordinator, ControlServer, PREFIX
from update_tls import backend as tls_backend, create_context, describe_error


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
                stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                env={**{k: v for k, v in os.environ.items() if not k.startswith(PREFIX)},
                     'QT_QPA_PLATFORM': 'offscreen'})
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


def prepare(installer, bundle, report, warning=None):
    current = installer.current()
    previous_version = current['version'] if current else None
    latest = None
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
    pending = installer.pending(REPOSITORY)
    if pending is not None:
        candidates.append((pending, installer.cached_archive(pending)))
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
            errors.append(f'Install {data["version"]}: {describe_error(exc)}')
    try:
        details = [f'Installed before: {previous_version or "none"}',
                   f'Latest verified: {latest["version"] if latest else "unavailable"}',
                   f'Selected: {current["version"] if current else "none"}',
                   f'TLS: {tls_backend()}']
        (installer.root / 'update.log').write_text('\n'.join(details + (errors or ['Up to date'])), encoding='utf-8')
    except OSError:
        pass
    if current is None:
        raise UpdateError('실행할 버전을 준비하지 못했습니다. 인터넷과 배포 ZIP을 확인하세요.\n'
                          + str(installer.root / 'update.log') + '\n' + '\n'.join(errors))
    if warning and errors and (latest is None or version(latest['version']) > version(current['version'])):
        reason = ('최신 버전을 확인하지 못했습니다.' if latest is None
                  else f'최신 v{latest["version"]} 업데이트를 적용하지 못했습니다.')
        if any('TLS certificate verification failed' in error for error in errors):
            reason += '\nHTTPS 인증서 발급기관을 확인하지 못했습니다. Windows 인증서·보안 프로그램·네트워크 검사를 확인하세요.'
        warning(reason + f'\n현재 설치된 v{current["version"]}로 실행합니다.'
                + '\n인터넷 연결을 확인한 뒤 다시 실행하거나 최신 ZIP을 새 폴더에 풀어 실행하세요.'
                + '\n진단 로그: ' + str(installer.root / 'update.log'))
    report(f'v{current["version"]} 시작 중…' + (' 업데이트 로그를 남겼습니다.' if errors else ''))
    return installer.executable(current)


def verify_live_update(installer, data, archive, check, log_path, runtime=None):
    """Run two actual game processes with a synthetic next Release in a sandbox."""
    import shutil
    import time
    first_version = data['version']
    major, minor, patch = version(first_version)
    target = dict(data, version=f'{major}.{minor}.{patch + 1}')
    asset = 'MorningBloom-python.zip' if installer.python_mode else 'MorningBloom-game.zip'
    target['url'] = f'https://github.com/{REPOSITORY}/releases/download/v{target["version"]}/{asset}'
    saves = installer.root / 'isolated-update-saves'
    saves.mkdir()
    def copy_payload(metadata, destination, report):
        shutil.copyfile(archive, destination)
        report('Synthetic release downloaded')
    coordinator = Coordinator(installer, REPOSITORY, check, saves,
        reader=lambda *args: target, downloader=copy_payload, interval=3600)
    server = ControlServer(coordinator)
    process = None
    try:
        with Path(log_path).open('a', encoding='utf-8') as log:
            for launch in range(2):
                current = installer.current()
                coordinator.started = False
                executable = installer.executable(current)
                env = server.environment(current)
                env[PREFIX + 'SMOKE_ROOT'] = str(saves)
                env[PREFIX + 'SMOKE_TARGET'] = target['version']
                process = subprocess.Popen(command(executable, runtime) + ['--live-update-smoke'],
                    cwd=executable.parent, env=env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                process.wait(timeout=35)
                if process.returncode != 0:
                    raise UpdateError(f'Live update process {launch} failed: {process.returncode}')
                if launch == 0:
                    if installer.current()['version'] != first_version:
                        raise UpdateError('Active version changed before old game exit')
                    if coordinator.activate_after_exit(process.returncode) is None:
                        raise UpdateError('Game did not commit an update before clean exit')
                else:
                    if coordinator.activate_after_exit(process.returncode) is not None:
                        raise UpdateError('Normal game exit unexpectedly restarted again')
            if installer.current()['version'] != target['version']:
                raise UpdateError('Live update did not activate the prepared version')
            if json.loads((saves / 'garden.json').read_text(encoding='utf-8'))['coins'] != 321:
                raise UpdateError('Garden changed during the update')
            log.write('Packaged live update, restart and garden preservation passed.\n')
    finally:
        if process is not None and process.poll() is None:
            process.kill()  # Only isolated smoke processes, never a user game.
            process.wait(timeout=5)
        server.close()


def diagnose(args):
    """Read-only checks: no game installs, save access, or launcher locks."""
    import urllib.parse
    import urllib.request
    lines = [f'TLS: {tls_backend()}']
    try:
        if args.tls_probe:
            url = urllib.parse.urlsplit(args.tls_probe)
            # Local fixture only. No arbitrary remote endpoints or credentials.
            if url.scheme != 'https' or url.hostname not in ('localhost', '127.0.0.1') or url.username or url.password:
                raise ValueError('TLS probe is restricted to HTTPS loopback fixtures')
            context = create_context(cafile=str(args.tls_ca) if args.tls_ca else None)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                urllib.request.HTTPSHandler(context=context))
            with opener.open(args.tls_probe, timeout=15) as response:
                response.read(1)
            lines.append('TLS probe: verified')
        else:
            create_context()  # Also proves the native backend is packaged.
            for mode in (False, True):
                data = read_latest(REPOSITORY, mode)
                lines.append(f'{"BAT" if mode else "EXE"} latest: {data["version"]}')
                if args.download_test:
                    with tempfile.TemporaryDirectory(prefix='bloom-update-check-') as temporary:
                        download(data, Path(temporary) / 'payload.zip')
                    lines.append(f'Payload size and SHA-256 verified: {data["size"]} bytes')
        result = 0
    except Exception as error:
        lines.append(describe_error(error))
        result = 1
    text = '\n'.join(lines) + '\n'
    if args.diagnostic_log:
        args.diagnostic_log.write_text(text, encoding='utf-8')
    elif sys.stdout:
        print(text, end='')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', action='store_true', dest='python_mode')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--verify-bundle', action='store_true')
    parser.add_argument('--diagnose-updates', action='store_true')
    parser.add_argument('--diagnostic-log', type=Path)
    parser.add_argument('--download-test', action='store_true')
    parser.add_argument('--tls-probe')
    parser.add_argument('--tls-ca', type=Path)
    args, game_args = parser.parse_known_args()
    if args.diagnose_updates or args.tls_probe:
        return diagnose(args)
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
                executable = installer.executable(data)
                runtime = python_runtime(executable, installer.root, lambda _: None) if args.python_mode else None
                verify_live_update(installer, data, bundle / archive, check, log_path, runtime)
        except Exception as exc:
            with log_path.open('a', encoding='utf-8') as log: log.write(str(exc) + '\n')
            return 1
        return 0
    root = tk.Tk()
    root.title('Morning Bloom')
    icon_root = Path(getattr(sys, '_MEIPASS', bundle))
    icon = icon_root / 'assets/icons/morning-bloom.ico'
    if icon.is_file():
        root.iconbitmap(str(icon))
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
    session = {'control': None, 'process': None, 'upgraded': False, 'rolled_back': False}

    def finish_session(message=None):
        if message:
            messagebox.showerror('Morning Bloom', message)
        if session['control']:
            session['control'].close()
        root.destroy()

    def launch_current():
        coordinator = session['control'].coordinator
        data = installer.current()
        executable = installer.executable(data)
        coordinator.started = False
        try:
            runtime = python_runtime(executable, installer.root, lambda text: status.set(text)) if args.python_mode else None
            active_args = list(game_args)
            if coordinator.restart_demo is not None:
                active_args = [arg for arg in active_args if arg != '--demo']
                if coordinator.restart_demo:
                    active_args.append('--demo')
            session['process'] = subprocess.Popen(command(executable, runtime) + active_args,
                cwd=str(executable.parent), env=session['control'].environment(data),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, UpdateError) as error:
            if session['upgraded'] and not session['rolled_back'] and coordinator.rollback_if_unchanged():
                session['upgraded'] = False
                session['rolled_back'] = True
                messagebox.showwarning('업데이트 복구', '새 버전을 시작하지 못해 이전 버전으로 돌아갑니다. 저장은 보존했습니다.')
                launch_current()
                return
            finish_session('게임 실행 실패 · ' + str(error))
            return
        root.withdraw()
        root.after(250, wait_game)

    def wait_game():
        process = session['process']
        if process.poll() is None:
            root.after(250, wait_game)
            return
        coordinator = session['control'].coordinator
        if session['upgraded'] and process.returncode and not coordinator.started:
            if not session['rolled_back'] and coordinator.rollback_if_unchanged():
                session['upgraded'] = False
                session['rolled_back'] = True
                messagebox.showwarning('업데이트 복구', '새 버전 시작에 실패해 이전 버전으로 돌아갑니다. 저장은 보존했습니다.')
                launch_current()
                return
            finish_session('새 버전 시작 실패 · 저장과 업데이트 전 백업을 보존했습니다. 새 저장을 구버전에 전달하지 않았습니다.\n' + str(installer.root / 'save-backups'))
            return
        previous = installer.current()
        try:
            applied = coordinator.activate_after_exit(process.returncode)
        except Exception as error:
            if installer.current() == previous:
                coordinator.control('cancel')
                session['upgraded'] = False
                messagebox.showwarning('업데이트 적용 실패', '정원과 이전 설치를 유지하고 게임을 다시 엽니다.\n' + str(error))
                launch_current()
            else:
                finish_session('업데이트 적용 실패 · 정원과 이전 설치를 보존했습니다.\n' + str(error))
            return
        if applied:
            session['upgraded'] = True
            launch_current()
        else:
            finish_session(f'게임이 종료되었습니다. 종료 코드: {process.returncode}' if process.returncode else None)

    def worker():
        try:
            exe = prepare(installer, bundle, lambda text: events.put(('status', text)),
                          warning=lambda text: events.put(('warning', text)))
            runtime = python_runtime(exe, installer.root, lambda text: events.put(('status', text))) if args.python_mode else None
            events.put(('ready', (command(exe, runtime) + game_args, exe.parent)))
        except Exception as exc: events.put(('error', str(exc)))
    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'status': status.set(value)
                elif kind == 'warning':
                    messagebox.showwarning('Morning Bloom · 업데이트 미적용', value)
                elif kind == 'error':
                    messagebox.showerror('Morning Bloom', '시작하지 못했습니다.\n' + value)
                    root.destroy()
                    return
                elif kind == 'ready':
                    def check(executable):
                        runtime = python_runtime(executable, installer.root, lambda text: None) if args.python_mode else None
                        return health_check(executable, installer.root / 'startup-check.log', runtime)
                    coordinator = Coordinator(installer, REPOSITORY, check, local / 'MorningBloomPython')
                    session['control'] = ControlServer(coordinator)
                    launch_current()
                    return
        except queue.Empty: pass
        root.after(100, poll)
    threading.Thread(target=worker, daemon=True).start()
    root.after(100, poll)
    root.mainloop()
    lock.close()
    return 0

if __name__ == '__main__': raise SystemExit(main())

