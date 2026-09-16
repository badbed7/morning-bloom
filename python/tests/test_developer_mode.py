import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QLockFile, QPoint, QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea

from morning_bloom.app import SETTINGS_PAGE, Window
from morning_bloom.model import Garden, HOUR
from morning_bloom.storage import SaveError, Store


NOW = 1_700_000_000


class DeveloperMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        font = Path(__file__).resolve().parents[2] / 'assets/fonts/NotoSansKR-Subset.otf'
        if font.exists():
            font_id = QFontDatabase.addApplicationFont(str(font))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                cls.app.setFont(QFont(families[0], 10))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.time_patch = patch('morning_bloom.app.time.time', return_value=NOW)
        self.wall_clock = self.time_patch.start()
        self.normal = Store(Path(self.temp.name) / 'garden.json')
        self.demo_store = Store(Path(self.temp.name) / 'demo-garden.json')
        garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True, coins=333)
        garden.plant(NOW)
        garden.care('water', NOW)
        garden.collection = [{
            'id': 'normal-flower', 'species': 'daisy', 'harvested_at': NOW,
            'base_sale_g': 50, 'misted': True, 'bonus_g': 5,
        }]
        self.normal.save(garden)
        lock = QLockFile(str(self.normal.path.with_suffix('.lock')))
        self.assertTrue(lock.tryLock(0))
        self.window = Window(self.normal, garden, save_lock=lock)

    def tearDown(self):
        self.window.clock.stop()
        self.window.autosave.stop()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.time_patch.stop()
        self.temp.cleanup()

    def prepare_demo(self, species='daisy', watered=True, two_pots=False):
        garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True, coins=200,
                        seeds={'daisy': 1, 'starflower': 1, 'tulip': 1})
        if two_pots:
            self.assertTrue(garden.buy_pot())
        self.assertTrue(garden.plant(NOW, species))
        if watered:
            self.assertTrue(garden.care('water', NOW))
        if two_pots:
            garden.select(1)
            garden.plant(NOW, 'starflower')
            garden.care('water', NOW)
        self.demo_store.save(garden)
        return garden

    def assert_unlocked(self, path):
        lock = QLockFile(str(path.with_suffix('.lock')))
        self.assertTrue(lock.tryLock(0))
        lock.unlock()

    def test_normal_mode_disables_time_skip_in_settings_and_method(self):
        self.assertFalse(self.window.developer_mode.isChecked())
        self.assertFalse(self.window.fast_forward_button.isEnabled())
        self.assertTrue(self.window.pages.widget(SETTINGS_PAGE).isAncestorOf(
            self.window.fast_forward_button
        ))
        before = self.window.garden.to_dict()
        self.window.fast_forward_button.click()
        self.assertFalse(self.window.fast_forward())
        self.assertEqual(self.window.offset, 0)
        self.assertEqual(self.window.garden.to_dict(), before)

    def test_checkbox_opens_separate_fresh_test_garden_and_restores_normal(self):
        shared_garden = self.window.garden
        self.window.developer_mode.setChecked(True)
        self.assertTrue(self.window.demo)
        self.assertEqual(self.window.store.path, self.demo_store.path)
        self.assertIn('개발자', self.window.title.text())
        self.assertTrue(self.window.fast_forward_button.isEnabled())
        self.assertEqual(self.window.garden.coins, 120)
        self.assertEqual(self.window.garden.collection, [])
        self.assertIs(self.window.garden, shared_garden)
        self.assertIs(self.window.flower.garden, shared_garden)
        self.assertIs(self.window.collection_garden.meadow.garden, shared_garden)
        normal_bytes = self.normal.path.read_bytes()
        self.window.plant_button.click()
        self.window.water_button.click()
        self.window.fast_forward_button.click()
        self.window.harvest_button.click()
        item_id = self.window.garden.collection[0]['id']
        self.assertTrue(self.window.sell_flower(item_id))
        self.assertEqual(self.normal.path.read_bytes(), normal_bytes)
        self.window.developer_mode.setChecked(False)
        self.assertFalse(self.window.demo)
        self.assertEqual(self.window.offset, 0)
        self.assertEqual(self.window.garden.coins, 333)
        self.assertEqual(self.window.garden.growth, 0)
        self.assertEqual(self.window.collection_garden.meadow.items[0]['id'], 'normal-flower')
        self.assertFalse(self.window.fast_forward_button.isEnabled())

    def test_six_hours_immediately_advances_both_pots_and_saves(self):
        self.prepare_demo(two_pots=True)
        self.assertTrue(self.window.set_developer_mode(True))
        self.window.fast_forward_button.click()
        self.assertEqual(self.window.offset, 6 * HOUR)
        self.assertEqual(self.window.garden.pots[0]['growth'], 6 * HOUR)
        self.assertEqual(self.window.garden.pots[1]['growth'], 3 * HOUR)
        self.assertEqual(self.window.garden.last_update, NOW + 6 * HOUR)
        self.assertEqual(self.demo_store.load(NOW).last_update, NOW + 6 * HOUR)
        self.assertEqual(self.wall_clock(), NOW)
        self.assertIn('6시간', self.window.developer_status.text())

    def test_six_hours_also_advances_sunlight_clock_to_pending_cap(self):
        demo = self.prepare_demo()
        demo.collection = [{
            'id': 'garden-flower', 'species': 'daisy', 'harvested_at': NOW,
            'base_sale_g': 50, 'misted': False, 'bonus_g': 0,
        }]
        demo.sun_intro_claimed = True
        self.demo_store.save(demo)
        self.window.set_developer_mode(True)
        self.window.fast_forward_button.click()
        self.assertEqual(len(self.window.garden.sun_tokens), 9)
        self.assertIn('대기 9/9', self.window.collection_garden.sun_status.text())

    def test_skip_does_not_bypass_first_water(self):
        self.prepare_demo(watered=False)
        self.window.set_developer_mode(True)
        self.window.fast_forward_button.click()
        self.assertEqual(self.window.garden.growth, 0)
        self.assertEqual(self.window.garden.pot['care_elapsed'], 0)
        self.window.water_button.click()
        self.window.fast_forward_button.click()
        self.assertEqual(self.window.garden.growth, 6 * HOUR)

    def test_skip_respects_vacation_and_resumes_without_catchup(self):
        self.prepare_demo()
        self.window.set_developer_mode(True)
        self.window.vacation.setChecked(True)
        self.window.fast_forward_button.click()
        self.assertEqual(self.window.garden.last_update, NOW + 6 * HOUR)
        self.assertEqual(self.window.garden.growth, 0)
        self.assertEqual(self.window.garden.pot['care_elapsed'], 0)
        self.assertIn('휴가', self.window.message.text())
        self.window.vacation.setChecked(False)
        self.window.fast_forward_button.click()
        self.assertEqual(self.window.garden.growth, 6 * HOUR)

    def test_repeated_skip_uses_tulip_watering_and_slow_growth_rules(self):
        self.prepare_demo('tulip')
        self.window.set_developer_mode(True)
        for _ in range(6):
            self.assertTrue(self.window.fast_forward())
        self.assertEqual(self.window.garden.pot['care_elapsed'], 36 * HOUR)
        self.assertEqual(self.window.garden.growth, 33 * HOUR)
        self.assertEqual(self.window.water_button.text(), '회복 물주기')
        self.window.water_button.click()
        self.window.fast_forward_button.click()
        self.assertEqual(self.window.garden.growth, 39 * HOUR)

    def test_return_to_normal_uses_only_real_elapsed_time(self):
        self.window.set_developer_mode(True)
        self.window.fast_forward_button.click()
        self.wall_clock.return_value = NOW + 1800
        self.assertTrue(self.window.set_developer_mode(False))
        self.assertEqual(self.window.garden.growth, 1800)
        self.assertEqual(self.window.garden.last_update, NOW + 1800)
        self.assertEqual(self.window.offset, 0)

    def test_reenter_demo_keeps_test_time_without_future_clock_freeze(self):
        self.prepare_demo()
        self.window.set_developer_mode(True)
        self.window.fast_forward_button.click()
        self.window.set_developer_mode(False)
        self.window.set_developer_mode(True)
        self.assertEqual(self.window.offset, 6 * HOUR)
        self.wall_clock.return_value += 30
        self.window.refresh()
        self.assertEqual(self.window.garden.growth, 6 * HOUR + 30)

    def test_direct_demo_launch_restores_clock_before_first_refresh(self):
        self.window.close()
        garden = self.prepare_demo()
        garden.advance(NOW + 12 * HOUR)
        self.demo_store.save(garden)
        lock = QLockFile(str(self.demo_store.path.with_suffix('.lock')))
        self.assertTrue(lock.tryLock(0))
        old_window = self.window
        self.window = Window(self.demo_store, self.demo_store.load(NOW), True, save_lock=lock)
        old_window.deleteLater()
        self.assertEqual(self.window.offset, 12 * HOUR)
        self.wall_clock.return_value += 60
        self.window.refresh()
        self.assertEqual(self.window.garden.growth, 12 * HOUR + 60)
        self.assertTrue(self.window.set_developer_mode(False))
        self.assertEqual(self.window.garden.growth, 60)

    def test_failed_skip_rolls_back_clock_growth_and_disk(self):
        self.prepare_demo()
        self.window.set_developer_mode(True)
        before = self.window.garden.to_dict()
        saved = self.demo_store.path.read_bytes()
        for error in (SaveError('디스크 실패'), OSError('접근 실패')):
            with self.subTest(error=type(error).__name__):
                with patch.object(self.window.store, 'save', side_effect=error):
                    self.assertFalse(self.window.fast_forward())
                self.assertEqual(self.window.offset, 0)
                self.assertEqual(self.window.garden.to_dict(), before)
                self.assertEqual(self.demo_store.path.read_bytes(), saved)
                self.assertIn('되돌렸습니다', self.window.message.text())

    def test_source_save_failure_cancels_mode_change_and_releases_target_lock(self):
        before = self.window.garden.to_dict()
        with patch.object(self.normal, 'save', side_effect=SaveError('저장 실패')):
            self.window.developer_mode.setChecked(True)
        self.assertFalse(self.window.demo)
        self.assertFalse(self.window.developer_mode.isChecked())
        self.assertIs(self.window.store, self.normal)
        self.assertEqual(self.window.garden.coins, before['coins'])
        self.assertFalse(self.demo_store.path.exists())
        self.assert_unlocked(self.demo_store.path)

    def test_target_save_failure_keeps_current_session(self):
        real_save = Store.save

        def fail_demo(store, garden):
            if store.path == self.demo_store.path:
                raise SaveError('테스트 저장 불가')
            return real_save(store, garden)

        with patch.object(Store, 'save', new=fail_demo):
            self.assertFalse(self.window.set_developer_mode(True))
        self.assertFalse(self.window.demo)
        self.assertIs(self.window.store, self.normal)
        self.assertIn('전환 실패', self.window.message.text())
        self.assertEqual(self.window.garden.coins, 333)
        self.assert_unlocked(self.demo_store.path)

    def test_failed_exit_keeps_developer_clock_and_controls(self):
        self.prepare_demo()
        self.window.set_developer_mode(True)
        self.window.fast_forward_button.click()
        before = self.window.garden.to_dict()
        with patch.object(self.window.store, 'save', side_effect=SaveError('테스트 저장 실패')):
            self.window.developer_mode.setChecked(False)
        self.assertTrue(self.window.demo)
        self.assertTrue(self.window.developer_mode.isChecked())
        self.assertTrue(self.window.fast_forward_button.isEnabled())
        self.assertEqual(self.window.offset, 6 * HOUR)
        self.assertEqual(self.window.garden.to_dict(), before)
        self.assert_unlocked(self.normal.path)

    def test_future_test_save_is_preserved_and_not_opened(self):
        original = '{"schema": 99}'
        self.demo_store.path.write_text(original, encoding='utf-8')
        with patch.object(self.normal, 'save') as save:
            self.assertFalse(self.window.set_developer_mode(True))
            save.assert_not_called()
        self.assertFalse(self.window.demo)
        self.assertEqual(self.demo_store.path.read_text(encoding='utf-8'), original)
        self.assertIn('새 버전', self.window.message.text())
        self.assert_unlocked(self.demo_store.path)

    def test_locked_destination_cancels_transition(self):
        other = QLockFile(str(self.demo_store.path.with_suffix('.lock')))
        self.assertTrue(other.tryLock(0))
        try:
            self.window.developer_mode.setChecked(True)
            self.assertFalse(self.window.demo)
            self.assertFalse(self.window.developer_mode.isChecked())
            self.assertIn('잠금', self.window.message.text())
        finally:
            other.unlock()

    def test_switch_transfers_save_lock_and_close_releases_it(self):
        self.window.set_developer_mode(True)
        self.assert_unlocked(self.normal.path)
        competing = QLockFile(str(self.demo_store.path.with_suffix('.lock')))
        self.assertFalse(competing.tryLock(0))
        self.window.close()
        self.assertIsNone(self.window._save_lock)
        self.assert_unlocked(self.demo_store.path)

    def test_window_settings_follow_each_separate_save(self):
        demo = self.prepare_demo()
        demo.settings.update(opacity=.8, topmost=False)
        self.demo_store.save(demo)
        self.window.set_developer_mode(True)
        self.assertEqual(self.window.opacity.value(), 80)
        self.assertFalse(self.window.topmost.isChecked())
        self.window.set_developer_mode(False)
        self.assertEqual(self.window.opacity.value(), 100)
        self.assertTrue(self.window.topmost.isChecked())

    def test_developer_tools_remain_accessible_in_small_scrolling_settings(self):
        self.window.show()
        self.window.settings_button.click()
        self.window.pages.finish_transition()
        scroll = self.window.pages.widget(SETTINGS_PAGE).findChild(QScrollArea)
        for size in (320, 384, 520):
            with self.subTest(size=size):
                self.window.setFixedSize(size, size)
                self.app.processEvents()
                scroll.ensureWidgetVisible(self.window.fast_forward_button)
                self.app.processEvents()
                button_rect = QRect(
                    self.window.fast_forward_button.mapTo(scroll.viewport(), QPoint(0, 0)),
                    self.window.fast_forward_button.size(),
                )
                self.assertTrue(scroll.viewport().rect().contains(button_rect))
                self.assertTrue(self.window.rect().contains(self.window.settings_button.geometry()))


if __name__ == '__main__':
    unittest.main()
