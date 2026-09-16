import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox

from morning_bloom.app import POT_PAGE, SHOP_PAGE, Window
from morning_bloom.model import Garden
from morning_bloom.storage import SaveError, Store


NOW = 1_700_000_000


class PotNavigation(unittest.TestCase):
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
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(
            NOW, tutorial_used=True, tutorial_reward_claimed=True, coins=200,
            seeds={'daisy': 1, 'starflower': 1, 'tulip': 0},
        )
        self.assertTrue(self.garden.buy_pot())
        self.assertTrue(self.garden.plant(NOW, 'daisy'))
        self.assertTrue(self.garden.care('water', NOW))
        self.garden.select(1)
        self.assertTrue(self.garden.plant(NOW, 'starflower'))
        self.garden.select(0)
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.window.persist())

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.time_patch.stop()
        self.temp.cleanup()

    def test_selector_uses_chevrons_and_seed_packets(self):
        self.assertFalse(hasattr(self.window, 'pot_picker'))
        self.assertEqual(
            self.window.pages.widget(POT_PAGE).findChildren(QComboBox),
            [],
        )
        self.assertEqual(set(self.window.species_picker.buttons), {'daisy', 'starflower', 'tulip'})
        self.assertTrue(all(not button.icon().isNull() for button in self.window.species_picker.buttons.values()))
        self.assertEqual(self.window.pot_name.text(), '화분 1 / 2 · 데이지')
        self.assertIn('성장 중', self.window.pot_name.toolTip())
        self.assertEqual(self.window.previous_pot.accessibleName(), '이전 화분')
        self.assertEqual(self.window.next_pot.accessibleName(), '다음 화분')

    def test_arrows_stop_at_both_ends_and_persist_valid_moves(self):
        before = self.garden.to_dict()
        for direction, expected in ((-1, 0), (1, 1), (1, 1), (-1, 0), (-1, 0)):
            boundary = self.garden.selected == expected
            with patch.object(self.store, 'save', wraps=self.store.save) as save:
                self.assertEqual(self.window.navigate_pot(direction), not boundary)
                if boundary:
                    save.assert_not_called()
            self.assertEqual(self.garden.selected, expected)
            self.assertIn(f'화분 {expected + 1} / 2', self.window.pot_name.text())
            self.assertEqual(self.store.load(NOW).selected, expected)
            self.assertEqual(self.window.previous_pot.isEnabled(), expected > 0)
            self.assertEqual(self.window.next_pot.isEnabled(), expected < 1)
            after = self.garden.to_dict()
            for key in ('pots', 'coins', 'seeds', 'collection', 'sunlight'):
                self.assertEqual(after[key], before[key], key)

    def test_slide_direction_matches_clicked_arrow(self):
        for button, direction in ((self.window.next_pot, 1), (self.window.previous_pot, -1)):
            QTest.mouseClick(button, Qt.LeftButton)
            slides = self.window.pot_slides
            self.assertIsNotNone(slides._animation)
            self.assertEqual(len(slides._overlays), 2)
            self.assertEqual(slides._animation.animationAt(1).startValue().x(),
                             slides.width() * direction)
            QTest.qWait(240)
            self.assertIsNone(slides._animation)
            self.assertEqual(slides._overlays, [])

    def test_single_pot_disables_arrows_until_second_pot_is_purchased(self):
        self.garden.pots.pop()
        self.garden.coins = 200
        self.window.refresh()
        self.assertEqual(self.window.pot_name.text(), '화분 1 / 1 · 데이지')
        with patch.object(self.store, 'save') as save:
            self.window.next_pot.click()
            self.assertFalse(self.window.navigate_pot(-1))
            save.assert_not_called()
        self.assertFalse(self.window.previous_pot.isEnabled())
        self.assertFalse(self.window.next_pot.isEnabled())
        original = dict(self.garden.pot)
        self.window.navigate(1)
        self.window.pages.finish_transition()
        self.assertEqual(self.window.pages.currentIndex(), SHOP_PAGE)
        self.window.buy_pot_button.click()
        self.window.navigate(-1)
        self.window.pages.finish_transition()
        self.assertFalse(self.window.previous_pot.isEnabled())
        self.assertTrue(self.window.next_pot.isEnabled())
        QTest.mouseClick(self.window.next_pot, Qt.LeftButton)
        self.assertEqual(self.window.pot_name.text(), '화분 2 / 2 · 빈 화분')
        self.assertEqual(self.garden.pots[0], original)

    def test_save_failure_restores_selected_pot_label_and_disk_without_animation(self):
        before = self.garden.to_dict()
        saved = self.store.path.read_bytes()
        label = self.window.pot_name.text()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.assertFalse(self.window.navigate_pot(1))
        self.assertEqual(self.garden.to_dict(), before)
        self.assertEqual(self.store.path.read_bytes(), saved)
        self.assertEqual(self.window.pot_name.text(), label)
        self.assertIsNone(self.window.pot_slides._animation)
        self.assertEqual(self.window.pot_slides._overlays, [])
        self.assertIn('되돌렸습니다', self.window.message.text())

    def test_care_targets_selected_pot_and_other_pots_continue_growing(self):
        self.window.flower.drops = 12
        QTest.mouseClick(self.window.next_pot, Qt.LeftButton)
        self.assertEqual(self.window.flower.drops, 0)
        self.assertEqual(self.window.water_button.text(), '첫 물주기')
        self.assertFalse(self.window.mist_button.isEnabled())
        self.window.pot_slides.finish_transition()
        QTest.mouseClick(self.window.water_button, Qt.LeftButton)
        QTest.mouseClick(self.window.mist_button, Qt.LeftButton)
        self.assertTrue(self.garden.pots[1]['initial_watered'])
        self.assertTrue(self.garden.pots[1]['misted'])
        self.assertFalse(self.garden.pots[0]['misted'])
        QTest.mouseClick(self.window.previous_pot, Qt.LeftButton)
        self.assertEqual(self.window.flower.drops, 0)
        self.assertFalse(self.window.water_button.isEnabled())
        self.assertTrue(self.window.mist_button.isEnabled())
        self.wall_clock.return_value = NOW + 600
        self.window.refresh()
        self.assertEqual([pot['growth'] for pot in self.garden.pots], [600, 660])

    def test_rapid_clicks_resize_and_leaving_page_clear_overlays(self):
        for _ in range(9):
            QTest.mouseClick(self.window.next_pot, Qt.LeftButton)
        self.assertEqual(self.garden.selected, 1)
        QTest.qWait(240)
        self.assertIsNone(self.window.pot_slides._animation)
        self.assertEqual(self.window.pot_slides._overlays, [])
        self.window.previous_pot.click()
        self.window.setFixedSize(384, 384)
        self.app.processEvents()
        self.assertEqual(self.window.pot_slides._overlays, [])
        self.window.next_pot.click()
        self.window.next_page.click()
        self.assertEqual(self.window.pot_slides._overlays, [])
        self.assertIsNone(self.window.pot_slides._animation)
        self.window.previous_page.click()
        self.window.pages.finish_transition()
        self.assertIn('화분 2 / 2', self.window.pot_name.text())

    def test_selection_survives_settings_and_restart(self):
        self.window.next_pot.click()
        self.window.settings_button.click()
        self.window.settings_button.click()
        self.window.pages.finish_transition()
        self.assertEqual(self.garden.selected, 1)
        restored = Window(self.store, self.store.load(NOW))
        try:
            self.assertEqual(restored.garden.selected, 1)
            self.assertIn('화분 2 / 2', restored.pot_name.text())
            self.assertEqual(restored.water_button.text(), '첫 물주기')
        finally:
            restored.close()
            restored.deleteLater()
            self.app.processEvents()

    def test_small_square_layout_keeps_selector_and_care_controls_inside(self):
        for side in (320, 384, 520):
            self.window.setFixedSize(side, side)
            self.app.processEvents()
            self.assertGreater(self.window.flower.height(), 0)
            for widget in (
                self.window.previous_pot, self.window.pot_name, self.window.next_pot,
                self.window.water_button, self.window.mist_button,
                self.window.fertilizer_button, self.window.settings_button,
            ):
                self.assertTrue(widget.isVisible())
                self.assertTrue(self.window.rect().contains(
                    widget.mapTo(self.window, widget.rect().topLeft())), side)
                self.assertTrue(self.window.rect().contains(
                    widget.mapTo(self.window, widget.rect().bottomRight())), side)
            self.assertLess(self.window.previous_pot.geometry().right(),
                            self.window.pot_name.geometry().left())
            self.assertLess(self.window.pot_name.geometry().right(),
                            self.window.next_pot.geometry().left())

    def test_switching_developer_gardens_refreshes_selection_and_arrow_availability(self):
        self.window.next_pot.click()
        self.assertTrue(self.window.set_developer_mode(True))
        self.assertEqual(self.window.pot_name.text(), '화분 1 / 1 · 빈 화분')
        self.assertFalse(self.window.next_pot.isEnabled())
        self.assertTrue(self.window.set_developer_mode(False))
        self.assertIn('화분 2 / 2', self.window.pot_name.text())
        self.assertFalse(self.window.next_pot.isEnabled())
        self.assertTrue(self.window.previous_pot.isEnabled())


if __name__ == '__main__':
    unittest.main()
