import json
import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom.app import SHOP_PAGE, Window
from morning_bloom.model import Garden, DAY, OFFLINE_CAP
from morning_bloom.plant_catalog import PLANTS, REGULAR_PLANTS, V10_REGULAR_PLANTS, VACATION_PLANTS, WEEKEND_PLANTS
from morning_bloom.storage import Store, SaveError, migrate
from morning_bloom.wind_game import WindState

NOW = 1_700_000_000
NEW_FLOWERS = ('rose', 'lily_of_the_valley', 'clover', 'sunflower', 'lavender', 'forget_me_not', *WEEKEND_PLANTS)


class NewFlowers(unittest.TestCase):
    def test_purchase_care_offline_harvest_and_sale_for_each_new_flower(self):
        for species in NEW_FLOWERS:
            with self.subTest(species=species):
                garden = Garden(NOW, coins=2000, tutorial_used=True, tutorial_reward_claimed=True)
                plant = PLANTS[species]
                self.assertTrue(garden.buy_seed(species))
                self.assertTrue(garden.plant(NOW, species))
                garden.advance(NOW + DAY)
                self.assertEqual(garden.growth, 0)
                self.assertTrue(garden.care('water', NOW + DAY))
                self.assertTrue(garden.care('mist', NOW + DAY))
                self.assertTrue(garden.harvest(NOW + DAY + plant.growth_seconds))
                garden = Garden.from_dict(garden.to_dict())
                self.assertTrue(garden.sell())
                self.assertEqual(garden.coins, 2000 - plant.seed_price + plant.sale_price + plant.mist_bonus)

    def test_long_flowers_pass_three_day_cap_but_honor_first_water_and_pause(self):
        for species in VACATION_PLANTS:
            garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True, seeds={species: 1})
            garden.plant(NOW, species)
            garden.advance(NOW + 30 * DAY)
            self.assertEqual(garden.growth, 0)
            garden.care('water', garden.last_update)
            garden.set_vacation(True, garden.last_update)
            garden.advance(NOW + 60 * DAY)
            self.assertEqual(garden.growth, 0)
            garden.set_vacation(False, garden.last_update)
            garden.advance(NOW + 90 * DAY)
            self.assertTrue(garden.bloomed)
            self.assertEqual(garden.growth, PLANTS[species].growth_seconds)
            self.assertEqual(garden.sunlight, 0)
        garden = Garden(NOW, tutorial_used=True, seeds={'rose': 1})
        garden.plant(NOW, 'rose')
        garden.care('water', NOW)
        garden.advance(NOW + 30 * DAY)
        self.assertEqual(garden.pot['care_elapsed'], OFFLINE_CAP)

    def test_v9_save_and_cloud_upgrade_preserve_every_existing_value(self):
        original = Garden(NOW, coins=456, sunlight=23).to_dict()
        original['schema'] = 9
        original['seeds'] = dict(daisy=2, starflower=4, tulip=6)
        expected = {**original, 'schema': Garden.CURRENT_SCHEMA,
                    'seeds': {**dict.fromkeys(REGULAR_PLANTS, 0), **original['seeds']}}
        raw = json.dumps(original)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            garden = store.load(NOW)
            self.assertEqual(garden.to_dict(), expected)
            store.save(garden)
            self.assertEqual(store.migration_backup.name, 'garden.json.v9-migration.bak')
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            self.assertEqual(store.replace_from_cloud(original, NOW).to_dict(), expected)
        self.assertEqual(original['seeds'], dict(daisy=2, starflower=4, tulip=6))
        broken = deepcopy(expected)
        broken['seeds'].pop('rose')
        with self.assertRaises(ValueError):
            Garden.from_dict(broken)
        original['seeds']['unknown'] = 1
        with self.assertRaises(ValueError):
            migrate(original)

    def test_weekend_flowers_bloom_at_two_three_four_days_after_reopening(self):
        for species, days in (('pansy', 2), ('cosmos', 3), ('freesia', 4)):
            with self.subTest(species=species), tempfile.TemporaryDirectory() as tmp:
                garden = Garden(NOW, tutorial_used=True, seeds={species: 1})
                self.assertEqual(PLANTS[species].growth_seconds, days * DAY)
                garden.plant(NOW, species)
                garden.care('water', NOW)
                garden.place_desktop(garden.pot['plant_id'], -160, 80)
                store = Store(Path(tmp) / 'garden.json')
                store.save(garden)
                before = store.load(NOW + days * DAY - 1)
                self.assertFalse(before.bloomed)
                reopened = store.load(NOW + days * DAY)
                self.assertTrue(reopened.bloomed)
                placement = deepcopy(reopened.desktop_flowers)
                self.assertTrue(reopened.harvest(reopened.last_update))
                store.save(reopened)
                self.assertEqual(store.load(reopened.last_update).desktop_flowers, placement)

    def test_v10_upgrade_preserves_newer_seeds_growing_flower_and_placement(self):
        garden = Garden(NOW, coins=456, sunlight=23, tutorial_used=True,
                        seeds={key: index + 1 for index, key in enumerate(V10_REGULAR_PLANTS)})
        garden.plant(NOW, 'lavender')
        garden.care('water', NOW)
        garden.place_desktop(garden.pot['plant_id'], -320, 120)
        original = garden.to_dict()
        original.update(schema=10, seeds={key: garden.seeds[key] for key in V10_REGULAR_PLANTS})
        raw = json.dumps(original)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            upgraded = store.load(NOW)
            self.assertEqual(upgraded.to_dict(), garden.to_dict())
            store.save(upgraded)
            self.assertEqual(store.migration_backup.name, 'garden.json.v10-migration.bak')
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            self.assertEqual(store.replace_from_cloud(original, NOW).to_dict(), garden.to_dict())
        for missing in ('rose', 'pansy'):
            broken = deepcopy(original if missing == 'rose' else garden.to_dict())
            broken['seeds'].pop(missing)
            with self.assertRaises(ValueError):
                Garden.from_dict(migrate(broken))


class WindPhysics(unittest.TestCase):
    def test_holding_or_releasing_forever_ends_without_idle_rewards(self):
        for held in (True, False):
            state = WindState(random.Random(42))
            for _ in range(600):
                state.step(1 / 60, held)
            self.assertTrue(state.ended)
            self.assertEqual(state.reward, 0)
            before = state.elapsed
            state.step(10, held)
            self.assertEqual(state.elapsed, before)

    def test_active_adjustment_can_collect_multiple_gates_and_increase_combo(self):
        state = WindState(random.Random(42))
        for _ in range(60 * 90):
            target = next((gate['y'] for gate in state.gates if not gate['checked']), .5)
            state.step(1 / 60, state.y + state.velocity * .65 > target)
        self.assertFalse(state.ended)
        self.assertGreaterEqual(state.hits, 20)
        self.assertGreater(state.score, state.hits)
        self.assertGreater(state.reward, 0)
        self.assertLess(len(state.gates), 5)
        self.assertGreaterEqual(state.radius, .08)

    def test_stall_and_duplicate_crossing_cannot_create_free_rewards(self):
        state = WindState(random.Random(42))
        state.gates = [dict(x=state.player_x + .001, y=state.y, checked=False)]
        state.step(30, False)
        self.assertLessEqual(state.elapsed, .101)
        self.assertEqual(state.hits, 1)
        state.step(.1, True)
        self.assertEqual(state.hits, 1)
        score = state.score
        for seconds in (float('nan'), float('inf'), -1):
            state.step(seconds, True)
        self.assertEqual(state.score, score)


class ContentUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = patch('morning_bloom.app.time.time', return_value=NOW)
        self.clock.start()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True)
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        self.window.cloud = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.clock.stop()
        self.temp.cleanup()

    def game(self):
        self.window.wind_button.click()
        self.app.processEvents()
        game = self.window._wind_game
        game.start_button.click()
        game.timer.stop()
        return game

    def test_all_seed_pages_are_reachable_and_fit_small_windows(self):
        for side in (320, 384, 520):
            self.window.setFixedSize(side, side)
            self.window.pages.setCurrentIndex(SHOP_PAGE)
            picker = self.window.shop_picker
            picker.buttons['daisy'].click()
            seen = set()
            while True:
                self.app.processEvents()
                visible = [(key, button) for key, button in picker.buttons.items() if button.isVisible()]
                self.assertLessEqual(len(visible), 3)
                for key, button in visible:
                    seen.add(key)
                    self.assertFalse(button.icon().isNull())
                    self.assertTrue(picker.rect().contains(button.geometry()))
                    self.assertGreaterEqual(button.width(), 58)
                    if key in WEEKEND_PLANTS:
                        self.assertIn('주말용', button.toolTip())
                        button.click()
                        self.assertIn('주말용', self.window.shop_info.text())
                self.assertTrue(picker.buttons[picker.selected].isVisible())
                if not picker.next.isEnabled():
                    break
                picker.next.click()
            self.assertEqual(seen, {*REGULAR_PLANTS, 'random'})
        self.assertEqual(self.garden.coins, 120)
        self.assertEqual(sum(self.garden.seeds.values()), 1)

    def test_mouse_keyboard_pause_and_opacity_follow_running_game(self):
        self.window.opacity.setValue(65)
        game = self.game()
        self.assertAlmostEqual(game.windowOpacity(), .65, delta=.01)
        QTest.mousePress(game.hold_button, Qt.LeftButton)
        self.assertIn('button', game.held_sources)
        QTest.keyPress(game, Qt.Key_Space)
        QTest.mouseRelease(game.hold_button, Qt.LeftButton)
        self.assertEqual(game.held_sources, {'keyboard'})
        QTest.keyRelease(game, Qt.Key_Space)
        self.assertFalse(game.held_sources)
        QTest.mousePress(game.canvas, Qt.LeftButton)
        self.assertIn('canvas', game.held_sources)
        QTest.mouseRelease(game.canvas, Qt.LeftButton)
        game.set_held('button', True)
        game.eventFilter(self.app, QEvent(QEvent.ApplicationDeactivate))
        self.assertTrue(game.paused)
        self.assertFalse(game.held_sources)
        before = game.state.elapsed
        with patch('morning_bloom.wind_game.time.monotonic', return_value=9_999_999):
            game.tick()
        self.assertEqual(game.state.elapsed, before)
        game.start_button.click()
        self.assertFalse(game.paused)
        self.assertTrue(game.timer.isActive())
        self.window.opacity.setValue(85)
        self.assertAlmostEqual(game.windowOpacity(), .85, delta=.01)
        QTest.keyClick(game, Qt.Key_Escape)
        self.assertIsNone(self.window._wind_game)
        self.assertEqual(self.garden.coins, 120)

    def test_rewards_save_once_allow_immediate_replay_and_retry_failed_save(self):
        game = self.game()
        game.state.score = 15
        game.finish_button.click()
        self.assertEqual(self.garden.coins, 123)
        old_id = game.game_id
        game.completed.emit(old_id, 3)
        self.assertEqual(self.store.load(NOW).coins, 123)
        game.start_button.click()
        game.timer.stop()
        self.assertNotEqual(game.game_id, old_id)
        game.completed.emit(old_id, 3)
        self.assertEqual(self.garden.coins, 123)
        game.state.score = 10
        with patch.object(self.store, 'save', side_effect=SaveError('full')):
            game.finish_button.click()
        self.assertEqual(self.garden.coins, 123)
        self.assertTrue(game.reward_pending)
        game.start_button.click()
        self.assertFalse(game.reward_pending)
        self.assertEqual(self.store.load(NOW).coins, 125)
        game.completed.emit(game.game_id, 2)
        self.assertEqual(self.garden.coins, 125)

    def test_garden_switch_closes_game_and_icons_have_transparent_background(self):
        game = self.game()
        game.state.score = 15
        self.assertTrue(self.window.set_developer_mode(True))
        self.assertIsNone(self.window._wind_game)
        self.assertEqual(self.garden.coins, 120)
        self.assertEqual(self.store.load(NOW).coins, 120)
        self.assertFalse(self.window.windowIcon().isNull())
        icon = QIcon(str(Path(__file__).resolve().parents[2] / 'assets/icons/morning-bloom.ico'))
        self.assertFalse(icon.isNull())
        for size in (16, 32, 48, 128, 256):
            image = icon.pixmap(size, size).toImage()
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            self.assertGreater(image.pixelColor(size // 2, size // 2).alpha(), 200)


if __name__ == '__main__':
    unittest.main()
