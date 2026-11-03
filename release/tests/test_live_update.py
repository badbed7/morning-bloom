"""Deterministic staging, session control, shutdown and rollback contracts."""

import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch

from live_update import Coordinator, ControlServer
from update_core import Installer, UpdateError, atomic_json

REPO = "badbed7/morning-bloom"


def payload(root, release):
    archive = root / (release + ".zip")
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("MorningBloomGame.exe", b"fake program " + release.encode())
    return archive, dict(
        protocol=1,
        version=release,
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        size=archive.stat().st_size,
        url=f"https://github.com/{REPO}/releases/download/v{release}/MorningBloom-game.zip",
    )


class LiveUpdate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.installer = Installer(self.root / "launcher")
        self.old_zip, self.old = payload(self.root, "0.8.11")
        self.new_zip, self.new = payload(self.root, "0.8.12")
        self.installer.install(self.old_zip, self.old, lambda _: True)
        self.saves = self.root / "saves"
        self.saves.mkdir()
        (self.saves / "garden.json").write_text('{"schema":15,"coins":123}')
        self.downloads = 0

        def download(data, path, report):
            self.downloads += 1
            path.write_bytes(self.new_zip.read_bytes())
            report("downloaded")

        self.coordinator = Coordinator(
            self.installer,
            REPO,
            lambda _: True,
            self.saves,
            reader=lambda *args: self.new,
            downloader=download,
            interval=3600,
        )

    def tearDown(self):
        self.coordinator.stop_event.set()
        self.temp.cleanup()

    def test_prepare_does_not_change_current_and_requires_commit_and_clean_exit(self):
        self.coordinator.check_once()
        self.assertEqual(self.installer.current()["version"], "0.8.11")
        self.assertTrue(self.coordinator.status()["ready"])
        self.assertIsNone(self.coordinator.activate_after_exit(0))
        self.coordinator.control("arm", "0.8.12")
        self.assertIsNone(self.coordinator.activate_after_exit(0))
        self.coordinator.control("commit", "0.8.12")
        self.assertIsNone(self.coordinator.activate_after_exit(1))
        applied = self.coordinator.activate_after_exit(0)
        self.assertEqual(applied["version"], "0.8.12")
        self.assertEqual(self.installer.current()["version"], "0.8.12")
        self.assertIsNone(self.coordinator.activate_after_exit(0))
        self.assertEqual(
            (self.coordinator.backup / "garden.json").read_bytes(),
            (self.saves / "garden.json").read_bytes(),
        )
        self.assertEqual(
            json.loads((self.installer.root / "previous.json").read_text())["version"],
            "0.8.11",
        )

    def test_cancel_never_restarts_and_target_is_pinned(self):
        self.coordinator.check_once()
        self.coordinator.reader = lambda *args: dict(self.new, version="0.8.13")
        self.coordinator.check_once()
        self.assertEqual(self.downloads, 1)
        self.assertEqual(self.coordinator.target["version"], "0.8.12")
        with self.assertRaises(UpdateError):
            self.coordinator.control("arm", "0.8.13")
        self.coordinator.control("arm", "0.8.12")
        self.coordinator.control("cancel")
        self.assertIsNone(self.coordinator.activate_after_exit(0))

    def test_pending_is_reused_after_restart_and_corruption_is_rejected(self):
        self.coordinator.check_once()
        pending = self.installer.pending(REPO)
        self.assertEqual(pending, self.new)
        second = Coordinator(
            self.installer,
            REPO,
            lambda _: True,
            self.saves,
            reader=lambda *args: self.new,
            downloader=lambda *args: self.fail("downloaded twice"),
        )
        second.check_once()
        self.assertTrue(second.status()["ready"])
        self.installer.cached_archive(self.new).write_bytes(b"partial")
        self.assertIsNone(self.installer.pending(REPO))
        self.assertEqual(self.installer.current()["version"], "0.8.11")

    def test_bad_hash_health_check_and_disk_failure_keep_live_install(self):
        for mode in ("hash", "health", "disk"):
            with self.subTest(mode=mode):
                coordinator = self.coordinator
                coordinator.target = None
                coordinator.check = lambda _: mode != "health"
                if mode == "hash":
                    coordinator.downloader = (
                        lambda data, path, report: path.write_bytes(b"bad")
                    )
                elif mode == "disk":

                    def disk(*args):
                        raise OSError("disk full")

                    coordinator.downloader = disk
                else:
                    coordinator.downloader = (
                        lambda data, path, report: path.write_bytes(
                            self.new_zip.read_bytes()
                        )
                    )
                coordinator.check_once()
                self.assertEqual(coordinator.status()["phase"], "error")
                self.assertEqual(self.installer.current()["version"], "0.8.11")
                self.assertEqual(
                    (self.saves / "garden.json").read_text(),
                    '{"schema":15,"coins":123}',
                )

    def test_duplicate_checks_share_one_download_and_status_remains_responsive(self):
        entered, resume = threading.Event(), threading.Event()

        def download(data, path, report):
            entered.set()
            if not resume.wait(3):
                raise RuntimeError("test timeout")
            path.write_bytes(self.new_zip.read_bytes())

        self.coordinator.downloader = download
        worker = threading.Thread(target=self.coordinator.check_once)
        worker.start()
        self.assertTrue(entered.wait(2))
        self.coordinator.check_once()
        self.assertEqual(self.coordinator.status()["phase"], "downloading")
        self.assertEqual(self.installer.current()["version"], "0.8.11")
        resume.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertTrue(self.coordinator.status()["ready"])

    def test_rollback_only_if_save_bytes_are_unchanged(self):
        self.coordinator.check_once()
        self.coordinator.control("arm", "0.8.12")
        self.coordinator.control("commit", "0.8.12")
        self.coordinator.activate_after_exit(0)
        original = (self.saves / "garden.json").read_bytes()
        (self.saves / "garden.json").write_text('{"schema":16,"coins":123}')
        self.assertFalse(self.coordinator.rollback_if_unchanged())
        self.assertEqual(self.installer.current()["version"], "0.8.12")
        self.assertEqual(
            json.loads((self.coordinator.backup / "garden.json").read_text())["schema"],
            15,
        )
        (self.saves / "garden.json").write_bytes(original)
        self.assertTrue(self.coordinator.rollback_if_unchanged())
        self.assertEqual(self.installer.current()["version"], "0.8.11")

    def test_authenticated_loopback_allows_only_fixed_commands(self):
        server = ControlServer(self.coordinator)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(path, token, body=b"{}"):
            request = urllib.request.Request(
                server.endpoint + path,
                data=body,
                headers={"Authorization": "Bearer " + token},
                method="POST",
            )
            return opener.open(request, timeout=2)

        try:
            for path, token, status in (
                ("/status", "wrong", 403),
                ("/execute", server.token, 404),
            ):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post(path, token)
                self.assertEqual(ctx.exception.code, status)
            with self.assertRaises(urllib.error.HTTPError):
                post("/arm", server.token, b'{"version":"C:/evil.exe"}')
            with post("/status", server.token) as response:
                self.assertEqual(json.load(response)["current"], "0.8.11")
            env = server.environment(self.old, {})
            self.assertEqual(env["MORNING_BLOOM_UPDATE_TOKEN"], server.token)
            self.assertNotIn(server.token, json.dumps(self.coordinator.status()))
        finally:
            server.close()
