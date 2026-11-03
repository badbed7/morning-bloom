"""Real loopback UI requests, save failures and close/backup coordination."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "release"))
from live_update import Coordinator, ControlServer
from update_core import Installer
from morning_bloom.app import Window
from morning_bloom.model import Garden
from morning_bloom.storage import Store, SaveError
from morning_bloom.update_client import UpdateClient
from morning_bloom.google_cloud import CloudError


class RuntimeUpdates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.installer = Installer(self.root / "launcher")
        items = []
        for release in ("0.8.11", "0.8.12"):
            archive = self.root / (release + ".zip")
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("MorningBloomGame.exe", release)
            data = dict(
                protocol=1,
                version=release,
                sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                size=archive.stat().st_size,
                url=f"https://github.com/badbed7/morning-bloom/releases/download/v{release}/MorningBloom-game.zip",
            )
            items.append((archive, data))
        self.old, self.new = items
        self.installer.install(*self.old, lambda _: True)
        self.saves = self.root / "saves"
        self.store = Store(self.saves / "garden.json")
        self.garden = Garden(time.time(), coins=432)
        self.window = Window(self.store, self.garden, True)
        self.window.clock.stop()
        self.window.autosave.stop()
        self.window.now = lambda: self.garden.last_update
        self.window.show()
        self.coordinator = Coordinator(
            self.installer,
            "badbed7/morning-bloom",
            lambda _: True,
            self.saves,
            reader=lambda *args: self.new[1],
            downloader=lambda data, path, report: path.write_bytes(
                self.new[0].read_bytes()
            ),
            interval=3600,
        )
        self.coordinator.check_once()
        self.server = ControlServer(self.coordinator)
        self.window.update_client.stop()
        self.window.update_client = UpdateClient(
            self.window, self.server.environment(self.old[1], {})
        )
        self.window.update_client.changed.connect(self.window._sync_update_controls)
        self.until(lambda: self.window.update_client.state.get("ready"))

    def until(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def tearDown(self):
        self.window._update_busy = self.window._update_closing = False
        self.window.cloud = None
        if self.window._gacha_board_window:
            self.window._gacha_board_window.done(0)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.server.close()
        self.temp.cleanup()

    def test_later_keeps_game_running_and_manual_apply_is_still_available(self):
        self.assertTrue(self.window.update_banner.isVisible())
        self.window.update_banner.hide()
        self.window._sync_update_controls(self.window.update_client.state)
        self.assertFalse(self.window.update_banner.isVisible())
        self.assertTrue(self.window.update_apply.isEnabled())
        self.assertFalse(self.coordinator.armed)
        self.assertEqual(self.installer.current()["version"], "0.8.11")

    def test_apply_saves_closes_and_commits_only_once(self):
        self.garden.desktop_scale = 170
        self.assertTrue(self.window.apply_live_update())
        self.assertFalse(self.window.apply_live_update())
        self.assertFalse(self.window.act(lambda: self.garden.buy_pot()))
        self.until(lambda: self.window._closing)
        self.assertTrue(self.coordinator.committed)
        self.assertTrue(self.coordinator.restart_demo)
        self.assertEqual(self.installer.current()["version"], "0.8.11")
        saved = self.store.load(self.garden.last_update)
        self.assertEqual((saved.coins, saved.desktop_scale), (432, 170))
        self.coordinator.activate_after_exit(0)
        self.assertEqual(self.installer.current()["version"], "0.8.12")

    def test_both_initial_and_final_save_failure_cancel_update(self):
        for final in (False, True):
            with self.subTest(final=final):
                original = self.store.save
                calls = [0]

                def save(garden):
                    calls[0] += 1
                    if not final or calls[0] >= 2:
                        raise SaveError("full")
                    original(garden)

                with patch.object(self.store, "save", side_effect=save):
                    result = self.window.apply_live_update()
                    if final:
                        self.assertTrue(result)
                        self.until(lambda: not self.window._update_busy)
                        self.until(lambda: not self.coordinator.armed)
                    else:
                        self.assertFalse(result)
                self.assertTrue(self.window.isVisible())
                self.assertFalse(self.coordinator.committed)
                self.assertEqual(self.installer.current()["version"], "0.8.11")
                self.window._sync_update_controls(self.window.update_client.state)

    def test_commit_failure_keeps_saved_game_open(self):
        original = self.window.update_client.request

        def request(action, offered="", **kwargs):
            if action == "commit":
                raise OSError("local channel lost")
            return original(action, offered, **kwargs)

        with patch.object(self.window.update_client, "request", side_effect=request):
            self.assertTrue(self.window.apply_live_update())
            self.until(lambda: not self.window._update_busy)
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.store.path.exists())
        self.assertFalse(self.coordinator.committed)

    def test_gacha_animation_skip_preserves_committed_results(self):
        self.window.open_gacha_board()
        dialog = self.window._gacha_board_window
        dialog.draw(10)
        before = self.garden.gacha.copy()
        self.assertTrue(dialog.animating)
        self.assertTrue(self.window.apply_live_update())
        self.until(lambda: self.window._closing)
        self.assertEqual(self.store.load(self.garden.last_update).gacha, before)
        self.assertEqual(self.garden.coins, 432)

    def test_cloud_failure_keeps_pending_marker_and_allows_saved_restart(self):
        class Cloud:
            configured = connected = True
            email = "test@example.com"

            def upload_save(self, data):
                raise CloudError("offline", code="network_error")

        self.window.demo = False
        self.window.cloud = Cloud()
        with patch("morning_bloom.app.QMessageBox.warning"):
            self.assertTrue(self.window.apply_live_update())
            self.until(lambda: self.window._closing)
        self.assertTrue(self.window._cloud_pending_path().exists())
        self.assertTrue(self.coordinator.committed)
        self.assertEqual(self.store.load(self.garden.last_update).coins, 432)

    def test_no_launcher_or_non_loopback_endpoint_disables_controls(self):
        for endpoint in (
            "https://evil.example",
            "http://localhost:123",
            "http://127.0.0.1:123/path",
            "http://user@127.0.0.1:123",
        ):
            env = self.server.environment(self.old[1], {})
            env["MORNING_BLOOM_UPDATE_ENDPOINT"] = endpoint
            client = UpdateClient(environment=env)
            self.assertFalse(client.available)
            self.assertFalse(client.command("check"))
            client.stop()
