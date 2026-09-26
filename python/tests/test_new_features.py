import json
import math
import tempfile
import unittest
from collections import Counter
from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from morning_bloom.app import SETTINGS_PAGE, Window
from morning_bloom.desktop_flowers import DesktopFlowers, sun_positions
from morning_bloom.desktop_host import DesktopUnavailable
from morning_bloom.flower_art import paint_collection_flower
from morning_bloom.model import Garden, V8_FIELDS, V12_FIELDS, FERTILIZER_CAP, REWARD_INTERVAL, empty_pot
from morning_bloom.plant_catalog import LEGACY_REGULAR_PLANTS, REGULAR_PLANTS, roll_mystery_seed
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
        for key in V8_FIELDS | V12_FIELDS:
            data.pop(key)
        data.update(schema=7, fertilizer=10, reward_wait=1750, last_reward_id='old')
        data['seeds'] = {key: data['seeds'][key] for key in LEGACY_REGULAR_PLANTS}
        raw = json.dumps(data)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            upgraded = store.load(NOW)
            self.assertEqual((upgraded.fertilizer, upgraded.fertilizer_reserve, upgraded.reward_wait), (5, 5, 130))
            for key in ('pots', 'coins', 'collection', 'settings', 'owned_skins'):
                self.assertEqual(upgraded.to_dict()[key], data[key])
            self.assertEqual(upgraded.seeds, {**dict.fromkeys(REGULAR_PLANTS, 0), **data['seeds']})
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
        for key in V8_FIELDS | V12_FIELDS:
            data.pop(key)
        data.update(schema=7, fertilizer=11)
        data['seeds'] = {key: data['seeds'][key] for key in LEGACY_REGULAR_PLANTS}
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

    def test_v8_migration_preserves_placements_and_backs_up_original(self):
        garden = collected()
        garden.place_desktop(garden.collection[0]['id'], -240, 100)
        data = {**garden.to_dict(), 'schema': 8}
        for key in V12_FIELDS:
            data.pop(key)
        data['seeds'] = {key: data['seeds'][key] for key in LEGACY_REGULAR_PLANTS}
        raw = json.dumps(data)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            upgraded = store.load(NOW)
            self.assertEqual(upgraded.to_dict(), {**garden.to_dict(), 'schema': Garden.CURRENT_SCHEMA})
            store.save(upgraded)
            self.assertEqual(store.migration_backup.name, 'garden.json.v8-migration.bak')
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            self.assertEqual(store.load(NOW).to_dict(), upgraded.to_dict())

    def test_growing_desktop_reference_survives_harvest_and_rejects_empty_pot(self):
        garden = growing()
        item_id = garden.pot['plant_id']
        self.assertTrue(garden.place_desktop(item_id, -320, 120))
        garden = Garden.from_dict(garden.to_dict())
        self.assertEqual(garden.collection, [])
        self.assertEqual(garden.sun_tokens, [])
        garden.growth = garden.duration
        self.assertTrue(garden.harvest(NOW))
        self.assertEqual(garden.desktop_flowers, {item_id: {'x': -320, 'y': 120}})
        self.assertEqual(garden.collection[0]['id'], item_id)
        self.assertFalse(garden.place_desktop(None, 0, 0))
        self.assertTrue(garden.sell(item_id))
        self.assertEqual(garden.desktop_flowers, {})

    def test_legacy_wait_without_reward_id_is_rejected_before_shortening(self):
        data = Garden(NOW).to_dict()
        for key in V8_FIELDS | V12_FIELDS:
            data.pop(key)
        data.update(schema=7, reward_wait=100, last_reward_id='')
        data['seeds'] = {key: data['seeds'][key] for key in LEGACY_REGULAR_PLANTS}
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


class FakeCloud:
    configured = True
    connected = True
    email = 'gardener@example.com'

    def __init__(self, download=None):
        self.download = download
        self.uploads = []

    def download_save(self):
        return self.download

    def upload_save(self, snapshot):
        self.uploads.append(deepcopy(snapshot))
        return NOW + 30


class InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.time_patch = patch('morning_bloom.app.time.time', return_value=NOW)
        self.wall_clock = self.time_patch.start()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = growing()
        self.window = Window(self.store, self.garden)
        self.window.desktop = DesktopFlowers(self.window, FakeDesktopHost)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        self.window.cloud = None
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

    def test_fertilizer_reward_wait_is_visible_and_counts_down(self):
        self.garden.reward_wait = 180
        self.garden.last_reward_id = 'visible-countdown'
        self.window.refresh()
        self.assertIn('3:00', self.window.fertilizer_stock.text())
        self.window.setFixedSize(320, 320)
        self.app.processEvents()
        widest_line = max(
            self.window.fertilizer_stock.fontMetrics().horizontalAdvance(line)
            for line in self.window.fertilizer_stock.text().splitlines()
        )
        self.assertLessEqual(widest_line, self.window.fertilizer_stock.width())
        self.wall_clock.return_value = NOW + 61
        self.window.refresh()
        self.assertIn('1:59', self.window.fertilizer_stock.text())
        self.wall_clock.return_value = NOW + 180
        self.window.refresh()
        self.assertIn('보상 가능', self.window.fertilizer_stock.text())

    def test_pot_flower_scale_does_not_change_with_notifications(self):
        for side, expected_height in ((320, 112), (384, 152), (520, 200)):
            self.window.setFixedSize(side, side)
            self.app.processEvents()
            before = (self.window.flower.width(), self.window.flower.height())
            self.window.notify(
                '저장 실패 · 기존 정원은 그대로 보존되며 잠시 후 다시 시도할 수 있습니다.\n두 번째 안내 줄',
                important=True,
            )
            self.app.processEvents()
            self.assertEqual((self.window.flower.width(), self.window.flower.height()), before)
            self.assertEqual(self.window.flower.height(), expected_height)
            self.window.notify('')
            self.app.processEvents()
            self.assertEqual((self.window.flower.width(), self.window.flower.height()), before)
            self.assertLess(
                self.window.water_button.mapTo(self.window, self.window.water_button.rect().bottomRight()).y(),
                self.window.height(),
            )

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

    def test_pot_collection_picker_uses_explicit_idempotent_floating_actions(self):
        self.garden.growth = self.garden.duration
        self.assertTrue(self.garden.harvest(NOW))
        self.window.refresh()
        self.assertEqual(self.window.collection_button.text(), '정원 꽃 1')
        self.window.open_collection_picker()
        self.app.processEvents()
        picker = self.window._collection_picker
        self.assertTrue(picker.isVisible())
        self.assertEqual(picker.list.count(), 1)
        item_id = self.garden.collection[0]['id']
        self.assertTrue(self.garden.place_desktop(item_id, 24, 36))
        picker.sync(force=True)
        self.assertIn('표시 복원 대기', picker.list.item(0).toolTip())
        self.assertTrue(picker.apply_action(item_id, True))
        self.assertEqual(set(self.window.desktop.windows), {item_id})
        self.assertTrue(picker.apply_action(item_id, True))
        self.assertEqual(set(self.window.desktop.windows), {item_id})
        self.assertIn('바탕화면 표시 중', picker.list.item(0).toolTip())
        self.assertTrue(picker.apply_action(item_id, False))
        self.assertEqual(self.window.desktop.windows, {})
        self.assertNotIn(item_id, self.garden.desktop_flowers)

    def test_growing_pot_menu_float_tracks_plant_through_selection_harvest_and_sale(self):
        item_id = self.garden.pot['plant_id']
        with patch('morning_bloom.app.QMenu') as menu_class:
            menu = menu_class.return_value
            menu.exec.return_value = menu.addAction.return_value
            self.window.flower.customContextMenuRequested.emit(QPoint(100, 80))
            menu.addAction.assert_called_once_with('화면 맨 위에 띄우기')
        widget = self.window.desktop.windows[item_id]
        self.assertTrue(widget.growing)
        self.assertEqual(widget.suns, {})
        self.assertIn(item_id, self.store.load(NOW).desktop_flowers)
        self.assertTrue(self.window.set_desktop_flower(item_id, True))
        self.assertIs(self.window.desktop.windows[item_id], widget)

        self.garden.pots.append(empty_pot())
        self.garden.selected = 1
        for ratio, stage in ((0, 0), (.1, 1), (.35, 2), (.7, 3), (1, 4)):
            self.garden.pots[0]['growth'] = self.garden.pots[0]['duration'] * ratio
            self.window.refresh()
            with patch('morning_bloom.desktop_flowers.paint_collection_flower',
                       wraps=paint_collection_flower) as paint:
                widget.grab()
            self.assertEqual(paint.call_args.kwargs['stage'], stage)
        self.assertTrue(widget.growing)
        self.assertEqual(widget.item['plant_id'], item_id)
        self.assertFalse(self.garden.planted)
        self.assertEqual(widget.suns, {})
        with patch('morning_bloom.app.QMenu') as menu_class:
            self.window.flower.customContextMenuRequested.emit(QPoint(100, 80))
            menu_class.assert_not_called()

        self.garden.selected = 0
        self.assertTrue(self.window.act(self.window.harvest_flower))
        self.assertIs(self.window.desktop.windows[item_id], widget)
        self.assertFalse(widget.growing)
        self.assertEqual(len(widget.suns), 1)
        self.assertTrue(self.window.sell_flower(item_id))
        self.assertNotIn(item_id, self.window.desktop.windows)

    def test_growing_pot_return_restore_and_save_failure_preserve_plant(self):
        item_id = self.garden.pot['plant_id']
        before = deepcopy(self.garden.pot)
        with patch.object(self.store, 'save', side_effect=SaveError('full')):
            self.assertFalse(self.window.set_desktop_flower(item_id, True))
        self.assertEqual(self.window.desktop.windows, {})
        self.assertEqual(self.garden.desktop_flowers, {})
        self.assertTrue(self.window.set_desktop_flower(item_id, True))
        position = deepcopy(self.garden.desktop_flowers[item_id])
        self.window.desktop.close()
        self.garden.restore(self.store.load(NOW).to_dict())
        self.window.desktop.sync()
        widget = self.window.desktop.windows[item_id]
        self.assertTrue(widget.growing)
        self.assertEqual(widget.host.position(int(widget.winId())), (position['x'], position['y']))
        with patch('morning_bloom.app.QMenu') as menu_class:
            menu = menu_class.return_value
            menu.exec.return_value = menu.addAction.return_value
            self.window.flower.customContextMenuRequested.emit(QPoint(100, 80))
            menu.addAction.assert_called_once_with('화분으로 돌려놓기')
        self.assertEqual(self.window.desktop.windows, {})
        self.assertEqual(self.garden.pot, before)

    def test_pot_collection_picker_handles_empty_and_large_collections(self):
        self.window.open_collection_picker()
        self.app.processEvents()
        picker = self.window._collection_picker
        self.assertTrue(picker.empty.isVisible())
        self.assertFalse(picker.list.isVisible())
        self.garden.collection = [{
            'id': f'stored-{index}', 'species': 'daisy', 'harvested_at': NOW,
            'base_sale_g': 50, 'misted': False, 'bonus_g': 0,
        } for index in range(100)]
        self.window.refresh()
        self.app.processEvents()
        self.assertEqual(picker.list.count(), 100)
        self.assertTrue(picker.list.isVisible())
        self.assertGreater(picker.list.verticalScrollBar().maximum(), 0)

    def test_minimize_preserves_floating_flowers_clock_and_normal_position(self):
        self.garden.collection.append({
            'id': 'stored-flower', 'species': 'daisy', 'harvested_at': NOW,
            'base_sale_g': 50, 'misted': False, 'bonus_g': 0,
        })
        self.window.refresh()
        self.assertTrue(self.window.set_desktop_flower('stored-flower', True))
        self.window.move(72, 84)
        self.app.processEvents()
        self.window.open_collection_picker()
        self.assertTrue(self.window._collection_picker.isVisible())
        self.window.minimize_button.click()
        self.app.processEvents()
        self.assertTrue(self.window.isMinimized())
        self.assertFalse(self.window._collection_picker.isVisible())
        self.assertIn('stored-flower', self.window.desktop.windows)
        self.assertTrue(self.window.clock.isActive())
        self.assertEqual((self.garden.settings['x'], self.garden.settings['y']), (72, 84))
        self.window.showNormal()
        self.app.processEvents()
        self.assertFalse(self.window.isMinimized())
        self.assertTrue(self.window.flower.timer.isActive())

    def test_cloud_restore_prompt_waits_until_window_is_restored(self):
        envelope = {'saved_at': NOW + 10, 'save': self.garden.to_dict()}
        self.window.showMinimized()
        self.app.processEvents()
        with patch('morning_bloom.app.QMessageBox.question', return_value=QMessageBox.No) as question:
            self.window._consider_cloud_save(envelope, manual=True)
            question.assert_not_called()
            self.assertIsNotNone(self.window._pending_cloud_prompt)
            self.window.showNormal()
            self.app.processEvents()
            question.assert_called_once()
            self.assertIsNone(self.window._pending_cloud_prompt)

    def test_connected_cloud_automatically_uploads_changed_local_save_every_five_minutes(self):
        cloud = FakeCloud()
        self.window.cloud = cloud
        self.window._sync_cloud_controls()

        def immediate(action, done, _message, silent_error=False):
            self.assertTrue(silent_error)
            done(action())
            return True

        with patch.object(self.window, '_run_cloud', side_effect=immediate) as run:
            self.assertTrue(self.window.auto_backup_cloud())

        self.assertEqual(self.window.cloud_auto.interval(), 5 * 60 * 1000)
        self.assertEqual(run.call_count, 2)  # conflict check, then upload
        self.assertEqual(len(cloud.uploads), 1)
        self.assertEqual(cloud.uploads[0], self.garden.to_dict())
        self.assertEqual(
            self.window._cloud_last_uploaded_digest,
            self.window._cloud_digest(self.garden.to_dict()),
        )
        state = json.loads(self.store.path.with_suffix('.cloud-sync.json').read_text(encoding='utf-8'))
        self.assertEqual(state['digest'], self.window._cloud_last_uploaded_digest)
        self.assertNotIn(cloud.email, json.dumps(state))
        expected_digest = self.window._cloud_last_uploaded_digest
        self.window._reset_cloud_state()
        self.window._load_cloud_state()
        self.assertEqual(self.window._cloud_last_uploaded_digest, expected_digest)
        self.assertIn('5분마다 자동 백업', self.window.cloud_status.text())
        self.assertIn('최근', self.window.cloud_status.text())

    def test_startup_download_applies_drive_save_before_auto_backup(self):
        remote = self.garden.to_dict()
        remote['coins'] += 31
        cloud = FakeCloud({'saved_at': NOW + 10, 'save': remote})
        self.window.cloud = cloud
        pending = {}

        def defer(action, done, _message, silent_error=False):
            self.assertFalse(silent_error)
            pending.update(action=action, done=done)
            return True

        with patch.object(self.window, '_run_cloud', side_effect=defer):
            self.assertTrue(self.window.startup_cloud_sync())
            self.assertFalse(self.window.pages.isEnabled())
            self.assertFalse(self.window.cloud_auto.isActive())
            self.assertEqual(cloud.uploads, [])
            pending['done'](pending['action']())

        self.assertEqual(self.window.garden.coins, remote['coins'])
        self.assertEqual(cloud.uploads, [])
        self.assertTrue(self.window.pages.isEnabled())
        self.assertTrue(self.window.cloud_auto.isActive())

    def test_unchanged_drive_save_does_not_prompt_again_after_startup_restore(self):
        remote = self.garden.to_dict()
        remote['last_update'] = NOW - 100
        envelope = {'saved_at': NOW - 10, 'save': remote}
        cloud = FakeCloud(envelope)
        self.window.cloud = cloud
        self.assertTrue(self.window._apply_cloud_save(envelope))
        self.assertEqual(self.window._cloud_last_uploaded_digest, self.window._cloud_digest(remote))

        def immediate(action, done, _message, silent_error=False):
            self.assertTrue(silent_error)
            done(action())
            return True

        with patch.object(self.window, '_run_cloud', side_effect=immediate), \
                patch('morning_bloom.app.QMessageBox.question', side_effect=AssertionError('false conflict')):
            self.assertTrue(self.window.auto_backup_cloud())
        self.assertEqual(len(cloud.uploads), 1)

    def test_close_uploads_latest_save_before_finishing(self):
        cloud = FakeCloud()
        self.window.cloud = cloud
        self.window.garden.coins += 9
        event = QCloseEvent()

        def immediate(action, done, _message, silent_error=False):
            done(action())
            return True

        with patch.object(self.window, '_run_cloud', side_effect=immediate), \
                patch.object(self.window, 'close') as close:
            self.window.closeEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertEqual(cloud.uploads[-1]['coins'], self.window.garden.coins)
        close.assert_called_once_with()

    def test_auto_backup_checks_newer_cloud_before_uploading(self):
        remote = self.garden.to_dict()
        remote['coins'] += 77
        cloud = FakeCloud({'saved_at': NOW + 10, 'save': remote})
        self.window.cloud = cloud
        self.window._cloud_known_saved_at = NOW
        self.window._cloud_last_uploaded_digest = self.window._cloud_digest(self.garden.to_dict())
        self.window._local_saved_at = NOW + 1000

        def immediate(action, done, _message, silent_error=False):
            self.assertTrue(silent_error)
            done(action())
            return True

        with patch.object(self.window, '_run_cloud', side_effect=immediate), \
                patch('morning_bloom.app.QMessageBox.question', return_value=QMessageBox.Yes) as question:
            self.assertTrue(self.window.auto_backup_cloud())

        question.assert_called_once()
        self.assertEqual(cloud.uploads, [])
        self.assertEqual(self.garden.coins, remote['coins'])

    def test_first_sync_on_new_pc_never_overwrites_different_cloud_without_confirmation(self):
        remote = self.garden.to_dict()
        remote['coins'] += 23
        cloud = FakeCloud({'saved_at': NOW - 1000, 'save': remote})
        self.window.cloud = cloud
        self.window._reset_cloud_state()

        def immediate(action, done, _message, silent_error=False):
            done(action())
            return True

        with patch.object(self.window, '_run_cloud', side_effect=immediate), \
                patch('morning_bloom.app.QMessageBox.question', return_value=QMessageBox.Yes) as question:
            self.assertTrue(self.window.auto_backup_cloud())

        question.assert_called_once()
        self.assertEqual(cloud.uploads, [])
        self.assertEqual(self.garden.coins, remote['coins'])

    def test_automatic_cloud_failure_stays_quiet_and_marks_next_retry(self):
        self.window.cloud = FakeCloud()
        failed = Future()
        failed.set_exception(OSError('offline'))
        self.window._cloud_future = failed
        self.window._cloud_done = lambda _: None
        self.window._cloud_busy = True
        self.window._cloud_silent_error = True

        with patch.object(self.window, 'notify') as notify:
            self.window._poll_cloud()

        notify.assert_not_called()
        self.assertTrue(self.window._cloud_auto_error)
        self.assertIn('다음 주기에 재시도', self.window.cloud_status.text())

    def test_floating_host_failure_preserves_garden(self):
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
