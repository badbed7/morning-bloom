"""End-to-end contracts for issues #1, #2, #7, #8."""

import io
import json
import tempfile
import time
import unittest
import urllib.error
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from morning_bloom import gacha_board as board
from morning_bloom.app import Window
from morning_bloom.cosmetics import THEMES, POT_SKINS
from morning_bloom.desktop_flowers import DesktopFlower
from morning_bloom.flower_art import paint_potted_flower
from morning_bloom.google_cloud import (
    CloudError,
    GoogleDriveSync,
    _request,
    authorize,
    TOKEN_URL,
    DRIVE_FILES_URL,
)
from morning_bloom.locked_catalog import COLLECTIONS, preview_image
from morning_bloom.model import Garden, V15_FIELDS, WIND_BASE_SECONDS
from morning_bloom.plant_catalog import PLANTS, SEED_PLANTS, GACHA_PLANTS
from morning_bloom.storage import Store, SaveError, migrate
from morning_bloom.wind_game import WindState

CLIENT = "test.apps.googleusercontent.com"


def draw_item(garden, category, tier, index):
    garden.sunlight = 100
    garden.gacha["tickets"] = 0
    garden.gacha["board"].update(position=0, sr_miss=0, ssr_miss=0)
    values = iter((0, 0, {"R": 9000, "SR": 1000, "SSR": 0}[tier], index))
    return garden.draw_gacha(category, randbelow=lambda n: next(values))[0]


class CollectionExpansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_reward_can_be_acquired_used_and_persisted(self):
        self.assertEqual((len(PLANTS), len(THEMES), len(POT_SKINS)), (22, 83, 45))
        self.assertEqual(
            sum(len(v) for c in board.REWARDS.values() for v in c.values()), 134
        )
        for category, tiers in board.REWARDS.items():
            for tier, pool in tiers.items():
                self.assertTrue(pool)
                for index, key in enumerate(pool):
                    with self.subTest(category=category, item=key):
                        garden = Garden(100, tutorial_used=True, coins=10000)
                        result = draw_item(garden, category, tier, index)
                        self.assertEqual(result["item"], key)
                        self.assertFalse(result["duplicate"])
                        if category == "plant":
                            self.assertEqual(garden.seeds[key], 1)
                            self.assertTrue(garden.buy_seed(key))
                            self.assertTrue(garden.plant(100, key))
                            self.assertTrue(garden.care("water", 100))
                            garden.advance(100 + PLANTS[key].growth_seconds)
                            self.assertTrue(garden.harvest(garden.last_update))
                            self.assertTrue(
                                garden.place_desktop(
                                    garden.collection[-1]["id"], -500, 200
                                )
                            )
                            self.assertTrue(garden.sell())
                            self.assertIn(key, garden.discovered_plants)
                            self.assertEqual(garden.seeds[key], 1)
                        elif category == "pot":
                            self.assertTrue(garden.equip_skin(key))
                        else:
                            self.assertTrue(garden.equip_theme(key))
                        clone = Garden.from_dict(garden.to_dict())
                        self.assertEqual(clone.to_dict(), garden.to_dict())
                        second = draw_item(garden, category, tier, index)
                        self.assertTrue(second["duplicate"])
                        if category == "plant":
                            self.assertEqual(garden.seeds[key], 1)
                        self.assertEqual(
                            second["leaves"], 1 + {"R": 1, "SR": 3, "SSR": 10}[tier]
                        )

    def test_multi_draw_duplicate_seeds_and_invalid_rng_are_atomic(self):
        garden = Garden(100, sunlight=100)
        # All ten rolls land on R except the last SR guarantee; repeat one item in each tier.
        values = iter([0, 0, 9000] * 10 + [0] * 10)
        result = garden.draw_gacha("plant", 10, lambda n: next(values))
        self.assertEqual(sum(garden.seeds[k] for k in GACHA_PLANTS), 2)
        self.assertEqual(sum(not r["duplicate"] for r in result), 2)
        before = garden.to_dict()
        garden.sunlight = 100
        before = garden.to_dict()
        values = iter([0, 0, 9000] * 10 + [0, 99999])
        self.assertFalse(garden.draw_gacha("plant", 10, lambda n: next(values)))
        self.assertEqual(garden.to_dict(), before)

    def test_cloud_restore_roundtrips_new_unlock_discovery_scale_and_upgrade(self):
        garden = Garden(100, coins=10000)
        draw_item(garden, "plant", "SSR", 0)
        garden.discovered_plants = ["daisy"]
        garden.set_desktop_scale(180)
        garden.buy_wind_upgrade("reward")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "garden.json")
            store.save(Garden(100, coins=77))
            restored = store.replace_from_cloud(garden.to_dict(), 100)
            self.assertEqual(restored.to_dict(), garden.to_dict())
            self.assertEqual(json.loads(store.cloud_backup.read_text())["coins"], 77)
            self.assertEqual(store.load(100).to_dict(), garden.to_dict())

    def test_locked_plants_and_cosmetics_cannot_be_bought(self):
        garden = Garden(0, coins=10000, sunlight=10000)
        before = garden.to_dict()
        for key in GACHA_PLANTS:
            self.assertFalse(garden.buy_seed(key))
            self.assertFalse(garden.plant(0, key))
        for key in THEMES:
            if key.startswith("catalog_"):
                self.assertFalse(garden.buy_theme(key, test_free=True))
        for key in POT_SKINS:
            if key.startswith("catalog_") or key == "rose":
                self.assertFalse(garden.buy_skin(key, test_free=True))
        self.assertEqual(garden.to_dict(), before)

    def test_all_runtime_art_and_growth_stages_render_without_text_sheet(self):
        for items in COLLECTIONS.values():
            for item in items:
                self.assertFalse(preview_image(item).isNull(), item.key)
        for key in GACHA_PLANTS:
            digests = []
            for stage in range(5):
                image = QImage(380, 180, QImage.Format_ARGB32)
                image.fill(Qt.transparent)
                painter = QPainter(image)
                paint_potted_flower(painter, PLANTS[key], stage=stage)
                painter.end()
                digests.append(bytes(image.bits()))
            self.assertEqual(len(set(digests)), 5, key)

    def test_v14_migration_preserves_old_ledger_and_rejects_bad_scale(self):
        current = Garden(
            100, sunlight=87, owned_skins=["terracotta", "rose"], equipped_skin="rose"
        )
        old = current.to_dict()
        old.pop('pot_skins')
        old.pop('pot_colors')
        old.pop('flower_pots')
        for key in V15_FIELDS:
            old.pop(key)
        old["seeds"] = {k: v for k, v in old["seeds"].items() if k not in GACHA_PLANTS}
        old["gacha"]["board"].pop("side_position")
        old["schema"] = 14
        source = deepcopy(old)
        converted = Garden.from_dict(migrate(old))
        self.assertEqual(old, source)
        self.assertEqual(converted.equipped_skin, "rose")
        self.assertEqual(converted.gacha, current.gacha)
        self.assertEqual(converted.sunlight, 87)
        for invalid in (True, 49, 201, 55, float("nan")):
            broken = converted.to_dict()
            broken["desktop_scale"] = invalid
            with self.assertRaises(ValueError):
                Garden.from_dict(broken)

    def test_old_history_remains_valid_with_larger_pools(self):
        garden = Garden(0)
        garden.gacha["history"] = [
            dict(
                position=56,
                board_gate=None,
                category="pot",
                rarity="SSR",
                item="rose",
                duplicate=False,
                leaves=1,
            )
        ]
        Garden.from_dict(garden.to_dict())


class Upgrades(unittest.TestCase):
    def test_upgrade_cost_caps_roundtrip_and_insufficient_balance(self):
        garden = Garden(100, coins=100000)
        for kind, maximum, field in (
            ("speed", 10, "wind_upgrade"),
            ("reward", 5, "wind_reward_upgrade"),
        ):
            for level in range(maximum):
                before = garden.coins
                price = garden.wind_upgrade_price(kind, level)
                self.assertTrue(garden.buy_wind_upgrade(kind))
                self.assertEqual(garden.coins, before - price)
                self.assertEqual(getattr(garden, field), level + 1)
            before = garden.to_dict()
            self.assertFalse(garden.buy_wind_upgrade(kind))
            self.assertEqual(garden.to_dict(), before)
        clone = Garden.from_dict(garden.to_dict())
        for hits in range(1, 11):
            clone.reward_wind_ring(hits)
        self.assertEqual(clone.coins, garden.coins + 6)
        self.assertFalse(Garden(0, coins=0).buy_wind_upgrade("speed"))

    def test_airborne_release_counts_and_ground_pauses(self):
        state = WindState(upgrade=10)
        state.step(0.1, False)
        self.assertAlmostEqual(state.progress, 0.1 * 1.15**10)
        state.y, state.velocity, state.grounded = 0.945, 0, True
        before = state.progress
        state.step(0.1, False)
        self.assertEqual(state.progress, before)


class WindowTransactions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "garden.json")
        self.garden = Garden(time.time())
        self.window = Window(self.store, self.garden, True)
        self.window.now = lambda: self.garden.last_update
        self.window.clock.stop()
        self.window.autosave.stop()

    def tearDown(self):
        if self.window._gacha_board_window:
            self.window._gacha_board_window.done(0)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_free_test_draws_preserve_integer_balances_and_rollback_all_unlocks(self):
        self.window.open_gacha_board()
        dialog = self.window._gacha_board_window
        dialog.category.setCurrentIndex(2)
        self.assertTrue(dialog.ten.isEnabled())
        before = self.garden.to_dict()
        with patch.object(self.store, "save", side_effect=SaveError("disk full")):
            dialog.draw(10)
        self.assertFalse(dialog.animating)
        self.assertEqual(self.garden.to_dict(), before)
        dialog.draw(10)
        dialog.finish_animation()
        self.assertEqual(self.garden.sunlight, before["sunlight"])
        self.assertEqual(self.garden.gacha["tickets"], before["gacha"]["tickets"])
        self.assertEqual(self.garden.gacha["board"]["total"], 10)
        self.assertEqual(type(self.garden.sunlight), int)
        self.window.set_test_sunlight(False)
        self.assertFalse(dialog.ten.isEnabled())
        self.window.demo = False
        self.window.set_test_sunlight(True)
        self.assertFalse(self.window.test_sunlight)

    def test_upgrade_and_scale_save_failure_roll_back(self):
        before = self.garden.to_dict()
        with patch.object(self.store, "save", side_effect=SaveError("full")):
            self.assertFalse(
                self.window.act(lambda: self.garden.buy_wind_upgrade("speed"))
            )
            self.assertFalse(
                self.window.act(lambda: self.garden.set_desktop_scale(200))
            )
        self.assertEqual(self.garden.to_dict(), before)

    def test_scaled_sun_hit_testing_uses_logical_coordinates(self):
        class Host:
            def valid(self, *args):
                return True

            def move(self, *args):
                pass

            def position(self, *args):
                return (0, 0)

            def detach(self, *args):
                pass

        self.garden.tutorial_used = True
        self.garden.plant(self.garden.last_update)
        key = self.garden.pot["plant_id"]
        self.garden.place_desktop(key, 0, 0)
        flower = DesktopFlower(self.window, key, Host())
        try:
            for scale in (50, 100, 200):
                self.garden.desktop_scale = scale
                flower.sync()
                self.assertEqual(flower.width(), round(256 * scale / 100))
                flower.suns = {"token": QPointF(128, 100)}
                self.assertEqual(
                    flower.sun_at(QPointF(128, 100) * (scale / 100)), "token"
                )
                self.assertIsNone(flower.sun_at(QPointF(250, 250) * (scale / 100)))
        finally:
            flower.dispose()


class CloudFailures(unittest.TestCase):
    def sync(self, credentials=None):
        return GoogleDriveSync(
            CLIENT,
            credentials or {"refresh_token": "private-token"},
            client_secret="private-secret",
        )

    def error(self, status, payload, url=TOKEN_URL):
        return urllib.error.HTTPError(
            url, status, "Bad Request", {}, io.BytesIO(json.dumps(payload).encode())
        )

    def test_stage_code_reason_are_kept_but_sensitive_description_is_not(self):
        cases = [
            (TOKEN_URL, "POST", "token"),
            (DRIVE_FILES_URL, "GET", "list"),
            (DRIVE_FILES_URL, "POST", "create"),
            (DRIVE_FILES_URL + "/x?alt=media", "GET", "download"),
            ("https://www.googleapis.com/upload/drive/v3/files/x", "PATCH", "upload"),
        ]
        for url, method, stage in cases:
            with patch(
                "urllib.request.urlopen",
                side_effect=self.error(
                    400,
                    {
                        "error": {
                            "message": "private-token",
                            "errors": [{"reason": "badRequest", "location": "q"}],
                        }
                    },
                    url,
                ),
            ):
                with self.assertRaises(CloudError) as ctx:
                    _request(url, method)
            self.assertEqual(
                (
                    ctx.exception.stage,
                    ctx.exception.status,
                    ctx.exception.reason,
                    ctx.exception.location,
                ),
                (stage, 400, "badRequest", "q"),
            )
            self.assertNotIn("private-token", str(ctx.exception))
            self.assertNotIn("다시 연결", ctx.exception.guidance)

    def test_invalid_grant_stops_background_retry_and_survives_restart(self):
        sync = self.sync()
        error = CloudError("failed", stage="token", status=400, code="invalid_grant")
        with patch(
            "morning_bloom.google_cloud._form_request", side_effect=error
        ) as request, patch("morning_bloom.google_cloud.save_credentials"):
            for _ in range(2):
                with self.assertRaises(CloudError):
                    sync.download_save()
            self.assertEqual(request.call_count, 1)
        self.assertFalse(sync.connected)
        self.assertFalse(sync.auto_retry_allowed)
        self.assertTrue(self.sync(sync.credentials).reauth_required)
        other = self.sync(
            {"refresh_token": "old", "client_id": "other.apps.googleusercontent.com"}
        )
        self.assertFalse(other.connected)

    def test_401_refreshes_once_and_403_is_not_retried(self):
        sync = self.sync()
        with patch(
            "morning_bloom.google_cloud._json_request",
            side_effect=[CloudError("expired", status=401), {"files": []}],
        ) as request, patch.object(sync, "_token", return_value="access"):
            self.assertIsNone(sync._file_id())
            self.assertEqual(request.call_count, 2)
        with patch(
            "morning_bloom.google_cloud._json_request",
            side_effect=CloudError("api", status=403, reason="accessNotConfigured"),
        ) as request, patch.object(sync, "_token", return_value="access"):
            with self.assertRaises(CloudError):
                sync._file_id()
            self.assertEqual(request.call_count, 1)
            self.assertFalse(sync.auto_retry_allowed)

    def test_callback_timeout_browser_failure_and_state_mismatch_are_distinct(self):
        for result, expected in (
            ({}, "시간이 만료"),
            ({"state": "wrong"}, "응답을 확인"),
        ):

            def callback(server, output, timeout):
                output.update(result)

            with patch(
                "morning_bloom.google_cloud._wait_for_callback", side_effect=callback
            ):
                with self.assertRaisesRegex(CloudError, expected):
                    authorize(CLIENT, browser_open=lambda url: True)
        with self.assertRaisesRegex(CloudError, "브라우저"):
            authorize(CLIENT, browser_open=lambda url: False)

    def test_transient_http_has_bounded_retry_without_retrying_create(self):
        for method, count in (("GET", 3), ("POST", 1)):
            errors = [self.error(503, {"error": {}}, DRIVE_FILES_URL) for _ in range(3)]
            with patch("urllib.request.urlopen", side_effect=errors) as request, patch(
                "time.sleep"
            ):
                with self.assertRaises(CloudError):
                    _request(DRIVE_FILES_URL, method)
                self.assertEqual(request.call_count, count)
