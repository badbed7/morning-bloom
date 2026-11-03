"""Launcher-owned update coordinator and authenticated loopback control channel."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from update_core import (
    UpdateError,
    atomic_json,
    download,
    manifest,
    read_latest,
    version,
)

PREFIX = "MORNING_BLOOM_UPDATE_"


class Coordinator:
    def __init__(
        self,
        installer,
        repository,
        check,
        save_root,
        *,
        reader=read_latest,
        downloader=download,
        interval=300,
    ):
        self.installer, self.repository, self.check = installer, repository, check
        self.save_root = Path(save_root)
        self.reader, self.downloader, self.interval = reader, downloader, interval
        self.lock = threading.RLock()
        self.stop_event, self.check_event = threading.Event(), threading.Event()
        self.state = dict(
            phase="idle",
            message="5분마다 새 버전을 확인합니다.",
            version="",
            current="",
            ready=False,
        )
        self.target = None
        self.armed = self.committed = self.started = False
        self.backup = None
        self.restart_demo = None
        self._busy = False

    def status(self):
        with self.lock:
            result = deepcopy(self.state)
            result["current"] = (self.installer.current() or {}).get("version", "")
            return result

    def report(self, message):
        with self.lock:
            self.state["message"] = message

    def request_check(self):
        with self.lock:
            if self.armed or self.target or self._busy:
                return
            self.state.update(phase="checking", message="새 버전 확인 중…", ready=False)
            self.check_event.set()

    def check_once(self):
        with self.lock:
            if self._busy or self.target or self.armed or self.stop_event.is_set():
                return
            self._busy = True
            self.state.update(phase="checking", message="새 버전 확인 중…", ready=False)
        try:
            data = manifest(
                self.reader(self.repository, self.installer.python_mode),
                self.repository,
                self.installer.python_mode,
            )
            current = self.installer.current()
            if current and version(data["version"]) <= version(current["version"]):
                with self.lock:
                    self.state.update(
                        phase="idle",
                        message="최신 버전입니다.",
                        version="",
                        ready=False,
                    )
                return
            with self.lock:
                self.state.update(
                    phase="downloading",
                    version=data["version"],
                    message="업데이트 다운로드 중…",
                )
            archive = self.installer.cached_archive(data)
            pending = self.installer.pending(self.repository)
            if pending != data:
                self.downloader(data, archive, self.report)
            if self.stop_event.is_set():
                return
            self.report("새 버전 설치 및 격리 실행 검사 중…")
            self.installer.stage(archive, data, self.check)
            if self.stop_event.is_set():
                return
            atomic_json(self.installer.pending_path, data)
            with self.lock:
                self.target = deepcopy(data)
                self.state.update(
                    phase="ready",
                    ready=True,
                    message=f'v{data["version"]} 업데이트 준비 완료',
                )
        except Exception as error:
            with self.lock:
                self.state.update(
                    phase="error",
                    ready=False,
                    message="업데이트 준비 실패 · " + str(error),
                )
        finally:
            with self.lock:
                self._busy = False

    def worker(self):
        while not self.stop_event.is_set():
            requested = self.check_event.wait(self.interval)
            self.check_event.clear()
            if self.stop_event.is_set():
                break
            self.check_once()

    def control(self, action, offered="", demo=None):
        with self.lock:
            if action == "hello":
                if offered != (self.installer.current() or {}).get("version"):
                    raise UpdateError("실행 버전이 일치하지 않습니다.")
                self.started = True
            elif action == "check":
                self.request_check()
            elif action == "cancel":
                self.armed = self.committed = False
            elif action in ("arm", "commit"):
                if not self.target or offered != self.target["version"]:
                    raise UpdateError("준비된 업데이트를 다시 확인하세요.")
                if action == "arm":
                    self.armed = True
                elif not self.armed:
                    raise UpdateError("업데이트 적용 요청이 없습니다.")
                else:
                    if demo is not None and type(demo) is not bool:
                        raise UpdateError("정원 모드 오류")
                    self.restart_demo = demo
                    self.committed = True
            elif action != "status":
                raise UpdateError("지원하지 않는 업데이트 요청")
            return self.status()

    def snapshot_saves(self):
        destination = self.installer.root / "save-backups" / uuid4().hex
        destination.mkdir(parents=True)
        if self.save_root.is_dir():
            for source in self.save_root.iterdir():
                if (
                    source.is_file()
                    and not source.is_symlink()
                    and (
                        source.name.endswith(".json")
                        or source.name.endswith(".bak")
                        or source.name.endswith(".pending")
                    )
                ):
                    shutil.copyfile(source, destination / source.name)
        atomic_json(
            destination / "update-backup.json",
            {
                "previous": self.installer.current(),
                "target": self.target["version"],
                "files": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in destination.iterdir()
                    if p.is_file()
                },
            },
        )
        self.backup = destination

    def activate_after_exit(self, returncode):
        """Called only after the launcher observes process termination."""
        with self.lock:
            if (
                returncode != 0
                or not self.armed
                or not self.committed
                or not self.target
            ):
                return None
            target = deepcopy(self.target)
            # A ready item stays pinned until application; no background replacement.
            self.snapshot_saves()
            self.installer.activate(target)
            self.armed = self.committed = self.started = False
            self.target = None
            self.state.update(
                phase="idle", ready=False, version="", message="업데이트 적용 완료"
            )
            return target

    def rollback_if_unchanged(self):
        """Never feed a modified/new-schema save into an older executable."""
        if not self.backup:
            return False
        metadata = json.loads((self.backup / "update-backup.json").read_text())
        expected = metadata["files"]
        actual = (
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.save_root.iterdir()
                if p.is_file()
                and (
                    p.name.endswith(".json")
                    or p.name.endswith(".bak")
                    or p.name.endswith(".pending")
                )
            }
            if self.save_root.is_dir()
            else {}
        )
        if actual != expected or not metadata["previous"]:
            return False
        previous = metadata["previous"]
        if not self.installer.executable(previous).is_file():
            return False
        atomic_json(self.installer.pointer, previous)
        self.backup = None
        return True


class ControlServer:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.token = secrets.token_hex(32)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if not secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + owner.token
                ):
                    self.send_error(403)
                    return
                action = self.path.removeprefix("/")
                if action not in (
                    "status",
                    "hello",
                    "check",
                    "arm",
                    "commit",
                    "cancel",
                ):
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= length <= 1024:
                        raise ValueError("Request too large")
                    self.connection.settimeout(2)
                    data = json.loads(self.rfile.read(length)) if length else {}
                    if not isinstance(data, dict) or set(data) - {"version", "demo"}:
                        raise ValueError("Invalid request")
                    result = owner.coordinator.control(
                        action, data.get("version", ""), data.get("demo")
                    )
                    status = 200
                except (ValueError, OSError, UpdateError) as error:
                    result, status = {"error": str(error)}, 409
                payload = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except OSError:
                    pass

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=coordinator.worker, daemon=True).start()

    def environment(self, current, base=None):
        env = dict(os.environ if base is None else base)
        env.update(
            {
                PREFIX + "ENDPOINT": self.endpoint,
                PREFIX + "TOKEN": self.token,
                PREFIX + "VERSION": current["version"],
            }
        )
        return env

    def close(self):
        self.coordinator.stop_event.set()
        self.coordinator.check_event.set()
        self.server.shutdown()
        self.server.server_close()
