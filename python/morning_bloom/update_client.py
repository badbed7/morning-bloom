"""Small authenticated client for the launcher owned update service."""

from concurrent.futures import Future
import json
import os
import re
from threading import Thread
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QTimer, Signal

PREFIX = "MORNING_BLOOM_UPDATE_"


class UpdateClient(QObject):
    changed = Signal(dict)

    def __init__(self, parent=None, environment=None):
        super().__init__(parent)
        env = os.environ if environment is None else environment
        self.endpoint = env.get(PREFIX + "ENDPOINT", "")
        self.token = env.get(PREFIX + "TOKEN", "")
        self.version = env.get(PREFIX + "VERSION", "")
        try:
            parsed = urllib.parse.urlsplit(self.endpoint)
            self.available = (
                parsed.scheme == "http"
                and parsed.hostname == "127.0.0.1"
                and parsed.port is not None
                and not parsed.username
                and not parsed.password
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
                and re.fullmatch("[a-f0-9]{64}", self.token) is not None
                and re.fullmatch(r"\d+\.\d+\.\d+", self.version) is not None
            )
        except ValueError:
            self.available = False
        self.future = None
        self.callback = None
        self.queued = None
        self.stopped = False
        self.state = dict(
            phase="unavailable",
            ready=False,
            version="",
            current=self.version,
            message="실행 중 업데이트를 사용하려면 새 ZIP의 BAT/런처로 실행하세요.",
        )
        self.poll = QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self.finish_request)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(lambda: self.command("status"))
        if self.available:
            QTimer.singleShot(0, lambda: self.command("hello", offered=self.version))
            self.refresh_timer.start()

    def request(self, action, offered="", demo=None):
        if not self.available or action not in (
            "status",
            "hello",
            "check",
            "arm",
            "commit",
            "cancel",
        ):
            raise ValueError("업데이트 런처 연결이 필요합니다.")
        request = urllib.request.Request(
            self.endpoint + "/" + action,
            data=json.dumps(
                {"version": offered, **({"demo": demo} if demo is not None else {})}
            ).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        # Loopback requests must not be sent through a configured system proxy.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=2
        ) as response:
            raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError("업데이트 응답이 너무 큽니다.")
            result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("업데이트 응답 오류")
        return result

    def command(self, action, callback=None, offered=""):
        if self.stopped or not self.available:
            return False
        if self.future is not None:
            if action != "status":
                self.queued = (action, callback, offered)
            return True
        self.future, self.callback = Future(), callback
        future = self.future

        def worker():
            try:
                future.set_result(self.request(action, offered))
            except Exception as error:
                future.set_exception(error)

        Thread(target=worker, daemon=True).start()
        self.poll.start()
        return True

    def finish_request(self):
        if self.future is None or not self.future.done():
            return
        future, callback = self.future, self.callback
        self.future = self.callback = None
        self.poll.stop()
        try:
            state, success = future.result(), True
        except Exception:
            state, success = (
                dict(
                    phase="error",
                    ready=False,
                    version="",
                    current=self.version,
                    message="업데이트 런처에 연결할 수 없습니다. 현재 게임은 계속 사용할 수 있습니다.",
                ),
                False,
            )
        self.state = state
        self.changed.emit(state)
        if callback:
            callback(success, state)
        queued, self.queued = self.queued, None
        if queued and not self.stopped:
            self.command(*queued[:2], offered=queued[2])

    def stop(self):
        self.stopped = True
        self.queued = None
        self.poll.stop()
        self.refresh_timer.stop()
