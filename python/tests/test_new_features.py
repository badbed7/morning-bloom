import json
import math
import tempfile
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom.app import SETTINGS_PAGE, Window
from morning_bloom.desktop_flowers import DesktopFlowers, sun_positions
from morning_bloom.desktop_host import DesktopUnavailable
from morning_bloom.model import Garden, V8_FIELDS, FERTILIZER_CAP, REWARD_INTERVAL
from morning_bloom.plant_catalog import roll_mystery_seed
from morning_bloom.storage import SaveError, Store, migrate

NOW = 1_700_000_000


def growing():
    garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True)
    garden.plant(NOW)
    garden.care('water', NOW)
    return garden


def collected():
    garden = growing()
    garden.growth = garden.duration
    garden.harvest(NOW)
    return garden


class RulesAndMigration(unittest.TestCase):
    def test_exact_thousand_ticket_odds(self):
        counts = Counter(roll_mystery_seed(lambda n, ticket=i: ticket) for i in range(1000))
        self.assertEqual(counts, {'ancient': 1, 'starflower': 333, 'daisy': 333, 'tulip': 333})

    def test_random_result_survives_reload_and_ancient_sells_for_500(self):
        garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True)
        with patch('morning_bloom.model.secrets.randbelow', return_value=0) as draw:
            self.assertTrue(garden.buy_seed('random'))
            draw.assert_called_once_with(1000)
        self.assertEqual(garden.coins, 100)
        garden = Garden.from_dict(garden.to_dict())
        with patch('morning_bloom.model.secrets.randbelow', side_effect=AssertionError('reroll')):
            self.assertTrue(garden.plant(NOW, 'random'))
        self.assertEqual(garden.species, 'ancient')
        self.assertTrue(garden.mystery_hidden)
        garden.care('water', NOW)
        self.assertTrue(garden.harvest(NOW + 48 * 3600))
        self.assertEqual(garden.mystery_plants, [])
        self.assertTrue(garden.sell())
        self.assertEqual(garden.coins, 600)
        self.assertFalse(garden.buy_seed('ancient'))

    def test_unaffordable_seed_does_not_draw_or_modify(self):
        garden = Garden(NOW, coins=19)
        before = garden.to_dict()
        with patch('morning_bloom.model.secrets.randbelow') as draw:
            self.assertFalse(garden.buy_seed('random'))
            draw.assert_not_called()
        self.assertEqual(garden.to_dict(), before)

    def test_v7_preserves_all_inventory_and_raw_backup(self):
        garden = growing()
        data = garden.to_dict()
        for key in V8_FIELDS:
            data.pop(key)
        data.update(schema=7, fertilizer=10, reward_wait=1750, last_reward_id='old')
        raw = json.dumps(data)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            upgraded = store.load(NOW)
            self.assertEqual((upgraded.fertilizer, upgraded.fertilizer_reserve, upgraded.reward_wait), (5, 5, 130))
            for key in ('pots', 'coins', 'seeds', 'collection', 'settings', 'owned_skins'):
                self.assertEqual(upgraded.to_dict()[key], data[key])
            store.save(upgraded)
            self.assertEqual(store.migration_backup.name, 'garden.json.v7-migration.bak')
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            self.assertTrue(upgraded.use_fertilizer(NOW))
            self.assertEqual((upgraded.fertilizer, upgraded.fertilizer_reserve), (5, 4))
            self.assertFalse(upgraded.reward_fertilizer('new', NOW + 180))
            store.save(upgraded)
            self.assertEqual(store.load(NOW + 180).fertilizer_reserve, 4)
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)

    def test_three_minute_boundary_and_five_item_cap(self):
        garden = growing()
        self.assertEqual((FERTILIZER_CAP, REWARD_INTERVAL), (5, 180))
        for i in range(5):
            self.assertTrue(garden.reward_fertilizer(str(i), NOW + i * 180))
            self.assertFalse(garden.reward_fertilizer('early', NOW + i * 180 + 179))
        self.assertFalse(garden.reward_fertilizer('full', NOW + 900))
        self.assertEqual(garden.fertilizer, 5)

    def test_new_fields_reject_corruption(self):
        data = collected().to_dict()
        for key, value in [('fertilizer', 6), ('fertilizer_reserve', -1), ('mystery_seeds', ['invalid']),
                           ('mystery_plants', ['missing']), ('desktop_opacity', float('nan')),
                           ('desktop_flowers', {'missing': {'x': 0, 'y': 0}})]:
            broken = deepcopy(data)
            broken[key] = value
            with self.assertRaises(ValueError, msg=key):
                Garden.from_dict(broken)

    def test_bad_legacy_inventory_is_not_silently_clamped(self):
        data = Garden(NOW).to_dict()
        for key in V8_FIELDS:
            data.pop(key)
        data.update(schema=7, fertilizer=11)
        with self.assertRaises(ValueError):
            migrate(data)

    def test_desktop_is_a_reference_not_a_duplicate_flower(self):
        garden = collected()
        flower_id = garden.collection[0]['id']
        self.assertTrue(garden.place_desktop(flower_id, -1200, 20))
        self.assertFalse(garden.place_desktop('missing', 0, 0))
        self.assertEqual(len(garden.collection), 1)
        garden = Garden.from_dict(garden.to_dict())
        token = garden.sun_tokens[0]['id']
        self.assertTrue(garden.collect_sun(token))
        self.assertFalse(garden.collect_sun(token))
        self.assertEqual(garden.sunlight, 1)
        self.assertTrue(garden.sell(flower_id))
        self.assertEqual(garden.desktop_flowers, {})

    def test_legacy_wait_without_reward_id_is_rejected_before_shortening(self):
        data = Garden(NOW).to_dict()
        for key in V8_FIELDS:
            data.pop(key)
        data.update(schema=7, reward_wait=100, last_reward_id='')
        with self.assertRaises(ValueError):
            migrate(data)

    def test_suns_stay_in_invisible_disk_with_separate_hit_targets(self):
        tokens = [{'id': f'token-{n}', 'created_at': n} for n in range(9)]
        positions = sun_positions(tokens)
        self.assertEqual(positions, sun_positions(tokens))
        for key, point in positions.items():
            self.assertLessEqual(math.hypot(point.x(), point.y()), 88)
            for other, target in positions.items():
                if key != other:
                    self.assertGreaterEqual(math.hypot(point.x() - target.x(), point.y() - target.y()), 30)


class FakeDesktopHost:
    def __init__(self):
        self.positions = {}

    def valid(self, hwnd=None):
        return hwnd is None or hwnd in self.positions

    def attach(self, widget, x, y):
        self.positions[int(widget.winId())] = (x, y)

    def move(self, widget, x, y):
        self.positions[int(widget.winId())] = (x, y)

    def position(self, hwnd):
        return self.positions[hwnd]

    def cursor_position(self):
        return 400, 400

    def detach(self, widget):
        self.positions.pop(int(widget.winId()), None)


class InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.time_patch = patch('morning_bloom.app.time.time', return_value=NOW)
        self.time_patch.start()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = growing()
        self.window = Window(self.store, self.garden)
        self.window.desktop = DesktopFlowers(self.window, FakeDesktopHost)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.time_patch.stop()
        self.temp.cleanup()

    def spray(self, canvas):
        QTest.mouseClick(canvas, Qt.LeftButton, pos=canvas.plant_rect().center().toPoint())
        for _ in range(12):
            canvas.animate()

    def test_three_sprays_apply_once_and_rapid_clicks_wait_for_animation(self):
        self.window.mist_button.click()
        game = self.window._mist_game
        self.assertIsNotNone(game)
        self.assertFalse(game.canvas.cursor().pixmap().isNull())
        QTest.mouseClick(game.canvas, Qt.LeftButton, pos=QPoint(1, 1))
        self.assertEqual(game.canvas.hits, 0)
        self.spray(game.canvas)
        self.spray(game.canvas)
        self.assertFalse(self.garden.pot['misted'])
        point = game.canvas.plant_rect().center().toPoint()
        QTest.mouseClick(game.canvas, Qt.LeftButton, pos=point)
        QTest.mouseClick(game.canvas, Qt.LeftButton, pos=point)
        self.assertEqual(game.canvas.hits, 3)
        self.assertFalse(self.garden.pot['misted'])
        for _ in range(12):
            game.canvas.animate()
        self.assertTrue(self.garden.pot['misted'])
        self.assertEqual(self.garden.pot['mist_count'], 1)
        game.finish_spraying()
        self.assertEqual(self.garden.pot['mist_count'], 1)
        self.assertTrue(self.store.load(NOW).pot['misted'])

    def test_cancel_and_save_failure_never_apply_partial_mist(self):
        before = self.garden.to_dict()
        self.window.open_mist_game()
        self.spray(self.window._mist_game.canvas)
        self.window._mist_game.reject()
        self.assertEqual(self.garden.to_dict(), before)
        self.window.open_mist_game()
        game = self.window._mist_game
        with patch.object(self.store, 'save', side_effect=SaveError('full')):
            for _ in range(3):
                self.spray(game.canvas)
        self.assertEqual(self.garden.to_dict(), before)
        self.assertIn('못했어요', game.result.text())

    def test_mode_switch_cancels_old_spray_without_touching_new_garden(self):
        self.window.open_mist_game()
        game = self.window._mist_game
        self.assertTrue(self.window.set_developer_mode(True))
        game.completed.emit()
        self.assertFalse(self.window.garden.planted)
        self.assertIsNone(self.window._mist_game)

    def test_fertilizer_accepts_input_immediately_without_dead_period(self):
        self.window.open_fertilizer_game()
        game = self.window._fertilizer_game
        self.app.processEvents()
        with patch('morning_bloom.fertilizer_game.time.monotonic', return_value=100) as clock:
            button = game.start_button
            QTest.mouseClick(button, Qt.LeftButton)
            self.assertIs(game.stop_button, button)
            clock.return_value = 100.05
            QTest.keyClick(game, Qt.Key_Space)
            self.assertEqual(game.round, 2)
            clock.return_value = 100.1
            QTest.keyClick(game, Qt.Key_Space)
            self.assertEqual(game.round, 3)

    def test_random_name_time_and_value_are_hidden_until_bloom(self):
        self.garden.growth = self.garden.duration
        self.garden.harvest(NOW)
        with patch('morning_bloom.model.secrets.randbelow', return_value=0):
            self.window.act(lambda: self.garden.buy_seed('random'))
        self.window.species_picker.buttons['random'].click()
        self.window.plant_button.click()
        self.window.water_button.click()
        for widget in (self.window.status, self.window.pot_name, self.window.remaining,
                       self.window.care_info, self.window.fertilizer_button, self.window.mist_button):
            self.assertNotIn('고대', widget.text() + widget.toolTip())
            self.assertNotIn('500', widget.text() + widget.toolTip())
            self.assertNotIn('48시간', widget.text() + widget.toolTip())
        self.assertFalse(self.window.progress.isVisible())
        self.garden.growth = self.garden.duration
        self.window.refresh()
        self.assertIn('고대 꽃', self.window.pot_name.text())

    def test_desktop_opacity_sun_collection_and_return_are_independent(self):
        self.garden.growth = self.garden.duration
        self.garden.harvest(NOW)
        item_id = self.garden.collection[0]['id']
        self.window.refresh()
        self.assertTrue(self.window.desktop.place(item_id))
        widget = self.window.desktop.windows[item_id]
        self.assertEqual(len(self.garden.collection), 1)
        self.assertEqual(self.window.collection_garden.meadow.tokens, [])
        self.assertTrue(self.window.pages.widget(SETTINGS_PAGE).isAncestorOf(self.window.desktop_opacity))
        self.window.desktop_opacity.setValue(40)
        self.assertAlmostEqual(widget.windowOpacity(), .4, delta=.01)
        self.assertEqual(self.garden.settings['opacity'], 1)
        token_id, point = next(iter(widget.suns.items()))
        QTest.mouseClick(widget, Qt.LeftButton, pos=point.toPoint())
        self.assertEqual(self.garden.sunlight, 1)
        self.assertFalse(self.garden.collect_sun(token_id))
        self.assertEqual(self.store.load(NOW).desktop_opacity, .4)
        self.assertTrue(self.window.desktop.place(item_id))
        self.assertEqual(self.window.desktop.windows, {})
        self.assertEqual(len(self.garden.collection), 1)

    def test_desktop_attachment_failure_does_not_create_floating_fallback(self):
        self.garden.growth = self.garden.duration
        self.garden.harvest(NOW)
        item_id = self.garden.collection[0]['id']
        before = self.garden.to_dict()
        self.window.desktop = DesktopFlowers(self.window, lambda: (_ for _ in ()).throw(DesktopUnavailable('unavailable')))
        self.assertFalse(self.window.desktop.place(item_id))
        self.assertEqual(self.garden.to_dict(), before)
        self.assertEqual(self.window.desktop.windows, {})

    def test_desktop_mode_switch_restores_original_placement(self):
        self.garden.growth = self.garden.duration
        self.garden.harvest(NOW)
        item_id = self.garden.collection[0]['id']
        self.assertTrue(self.window.desktop.place(item_id))
        widget = self.window.desktop.windows[item_id]
        host = widget.host
        hwnd = int(widget.winId())
        placement = deepcopy(self.garden.desktop_flowers)
        self.assertTrue(self.window.set_developer_mode(True))
        self.assertNotIn(hwnd, host.positions)
        self.assertEqual(self.window.desktop.windows, {})
        self.assertTrue(self.window.set_developer_mode(False))
        self.assertEqual(self.window.garden.desktop_flowers, placement)
        self.assertIn(item_id, self.window.desktop.windows)
        self.assertEqual(len(self.window.garden.collection), 1)

    def test_desktop_failed_save_closes_tentative_window(self):
        self.garden.growth = self.garden.duration
        self.garden.harvest(NOW)
        item_id = self.garden.collection[0]['id']
        with patch.object(self.store, 'save', side_effect=SaveError('full')):
            self.assertFalse(self.window.desktop.place(item_id))
        self.assertEqual(self.garden.desktop_flowers, {})
        self.assertEqual(self.window.desktop.windows, {})


if __name__ == '__main__':
    unittest.main()
