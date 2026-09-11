"""Stable Windows bootstrap. Keeps its lock until the game exits."""
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
from update_core import Installer, read_latest, manifest, download, version


def health_check(executable):
    try:
        result = subprocess.run([str(executable), '--smoke-test'], timeout=45,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired): return False


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
    # The complete first distribution works offline; saves live elsewhere.
    if current is None:
        report('Preparing first launch...')
        data = manifest(json.loads((bundle / 'bundled-update.json').read_text()), REPOSITORY)
        current = installer.install(bundle / 'MorningBloom-game.zip', data, health_check)
    try:
        report('Checking for updates...')
        latest = read_latest(REPOSITORY)
        if version(latest['version']) > version(current['version']):
            with tempfile.TemporaryDirectory(prefix='download-', dir=installer.root) as temp:
                archive = Path(temp) / 'game.zip'
                download(latest, archive, report)
                report('Checking new version...')
                current = installer.install(archive, latest, health_check)
    except Exception as exc:
        # No credentials are ever stored in the launcher. Offline/private feeds fail closed.
        try: (installer.root / 'update.log').write_text(f'Update unavailable: {type(exc).__name__}: {exc}\n', encoding='utf-8')
        except OSError: pass
        report('Update unavailable. Starting installed version...')
    return installer.executable(current)


def main():
    if '--self-test' in sys.argv:
        version('0.3.0')
        return 0
    if '--verify-bundle' in sys.argv:
        bundle = Path(sys.executable).parent
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp)
            data = manifest(json.loads((bundle / 'bundled-update.json').read_text()), REPOSITORY)
            installer.install(bundle / 'MorningBloom-game.zip', data, health_check)
        return 0
    root = tk.Tk()
    root.title('Morning Bloom')
    root.geometry('400x120')
    root.resizable(False, False)
    status = tk.StringVar(value='Starting Morning Bloom...')
    tk.Label(root, textvariable=status, padx=20, pady=35).pack()
    root.protocol('WM_DELETE_WINDOW', lambda: None)
    installer = Installer(Path(os.environ['LOCALAPPDATA']) / 'MorningBloomLauncher')
    lock = acquire_lock(installer.root / 'launcher.lock')
    if lock is None:
        messagebox.showinfo('Morning Bloom', 'Morning Bloom is already running.')
        root.destroy()
        return 0
    bundle = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    events = queue.Queue()
    def worker():
        try:
            exe = prepare(installer, bundle, lambda text: events.put(('status', text)))
            events.put(('ready', exe))
        except Exception as exc: events.put(('error', str(exc)))
    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'status': status.set(value)
                elif kind == 'error':
                    messagebox.showerror('Morning Bloom', 'Unable to start.\n' + value)
                    root.destroy()
                    return
                elif kind == 'ready':
                    try:
                        process = subprocess.Popen([str(value)], cwd=str(value.parent))
                    except OSError as exc:
                        messagebox.showerror('Morning Bloom', str(exc));root.destroy();return
                    root.withdraw()
                    def wait_game():
                        if process.poll() is None: root.after(500, wait_game)
                        else: root.destroy()
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
