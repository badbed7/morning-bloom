import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea

from morning_bloom.app import POT_PAGE, SHOP_PAGE, Window
from morning_bloom.model import Garden, HOUR
from morning_bloom.storage import SaveError, Store


class FailingStore:
    notice = ''

    def save(self, state):
        raise SaveError('테스트 저장 실패')


class UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tutorial_click_loop_requires_water(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            window = Window(store, Garden(time.time()), True)
            window.show()
            self.app.processEvents()
            window.plant_button.click()
            window.offset = 61
            window.refresh()
            self.assertFalse(window.harvest_button.isEnabled())
            window.water_button.click()
            window.offset = 122
            window.refresh()
            self.assertTrue(window.harvest_button.isEnabled())
            window.harvest_button.click()
            flower = window.collection_garden.meadow.items[0]
            self.assertIn('50G', window.collection_garden.meadow.tooltip_for(flower))
            window.close()

    def test_starflower_mist_sale_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(time.time(), tutorial_used=True, tutorial_reward_claimed=True,
                            seeds={'daisy': 0, 'starflower': 1, 'tulip': 0})
            window = Window(store, garden, True)
            window.species_picker.buttons['starflower'].click()
            self.assertIn('3시간', window.species_picker.buttons['starflower'].toolTip())
            window.plant_button.click()
            window.water_button.click()
            window.mist_button.click()
            canvas = window._mist_game.canvas
            for _ in range(3):
                QTest.mouseClick(canvas, Qt.LeftButton, pos=canvas.plant_rect().center().toPoint())
                for _ in range(12):
                    canvas.animate()
            window._mist_game.accept()
            window.offset = 3 * HOUR + 1
            window.refresh()
            window.harvest_button.click()
            flower = window.collection_garden.meadow.items[0]
            tooltip = window.collection_garden.meadow.tooltip_for(flower)
            self.assertIn('13G', tooltip)
            self.assertIn('분무 +1G', tooltip)
            self.assertTrue(window.sell_flower(flower['id']))
            self.assertEqual(garden.coins, 133)
            window.close()

    def test_tulip_slow_status_and_recovery_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(time.time(), tutorial_used=True, tutorial_reward_claimed=True,
                            seeds={'daisy': 0, 'starflower': 0, 'tulip': 1})
            window = Window(store, garden, True)
            window.species_picker.buttons['tulip'].click()
            window.plant_button.click()
            garden.pot.update(ruleset_id='v0.4', care_profile='tulip_midwater', fertilizer_limit=0)
            window.water_button.click()
            window.offset = 40 * HOUR
            window.refresh()
            self.assertEqual(window.water_button.text(), '회복 물주기')
            self.assertIn('50% 속도', window.care_info.text())
            window.water_button.click()
            self.assertEqual(window.water_button.text(), '물주기 완료')
            window.close()

    def test_failed_action_save_rolls_back(self):
        garden = Garden(time.time())
        window = Window(FailingStore(), garden, True)
        window.plant_button.click()
        self.assertFalse(garden.planted)
        self.assertEqual(garden.seed_count('daisy'), 1)
        self.assertIn('되돌렸습니다', window.message.text())
        window.clock.stop()
        window.autosave.stop()
        window.hide()

    def test_seed_packets_select_buy_and_plant_without_accidental_spending(self):
        with tempfile.TemporaryDirectory() as tmp, patch('morning_bloom.app.time.time', return_value=1_700_000_000):
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(time.time(), tutorial_used=True, tutorial_reward_claimed=True,
                            seeds={'daisy': 0, 'starflower': 0, 'tulip': 0}, coins=40)
            window = Window(store, garden)
            window.show()
            self.app.processEvents()
            try:
                window.persist()
                saved = store.path.read_bytes()
                window.navigate(1)
                window.pages.finish_transition()
                self.assertEqual(window.pages.widget(SHOP_PAGE).findChildren(QComboBox), [])
                window.shop_picker.buttons['tulip'].click()
                window.shop_picker.buttons['starflower'].click()
                self.assertEqual(sum(button.isChecked() for button in window.shop_picker.buttons.values()), 1)
                self.assertEqual((garden.coins, sum(garden.seeds.values())), (40, 0))
                self.assertEqual(store.path.read_bytes(), saved)
                self.assertIn('8G', window.buy_seed_button.text())
                window.buy_seed_button.click()
                self.assertEqual((garden.coins, garden.seed_count('starflower')), (32, 1))
                self.assertIn('1개', window.species_picker.buttons['starflower'].text())
                self.assertEqual(window.species_picker.selected, 'daisy')
                before = garden.to_dict()
                with patch.object(store, 'save', side_effect=SaveError('disk full')):
                    window.buy_seed_button.click()
                self.assertEqual(garden.to_dict(), before)
                window.navigate(-1)
                window.pages.finish_transition()
                self.assertEqual(window.pages.widget(POT_PAGE).findChildren(QComboBox), [])
                self.assertFalse(window.plant_button.isEnabled())
                window.species_picker.buttons['starflower'].setFocus()
                QTest.keyClick(window.species_picker.buttons['starflower'], Qt.Key_Space)
                self.assertEqual(window.species_picker.selected, 'starflower')
                self.assertTrue(window.plant_button.isEnabled())
                window.plant_button.click()
                self.assertEqual((garden.pot['species'], garden.seed_count('starflower')), ('starflower', 0))
                self.assertEqual(store.load(time.time()).pot['species'], 'starflower')
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_seed_packets_and_plant_button_fit_small_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = Window(Store(Path(tmp) / 'garden.json'),
                            Garden(time.time(), tutorial_used=True, tutorial_reward_claimed=True))
            window.show()
            try:
                for side in (320, 384, 520):
                    window.setFixedSize(side, side)
                    self.app.processEvents()
                    for button in (*(button for button in window.species_picker.buttons.values() if button.isVisible()), window.plant_button):
                        self.assertTrue(button.isVisible())
                        self.assertTrue(window.rect().contains(button.mapTo(window, button.rect().topLeft())))
                        self.assertTrue(window.rect().contains(button.mapTo(window, button.rect().bottomRight())))
                    buttons = [button for button in window.species_picker.buttons.values() if button.isVisible()]
                    for left, right in zip(buttons, buttons[1:]):
                        self.assertLess(left.geometry().right(), right.geometry().left())
                    window.notify('저장 실패 · 행동을 되돌렸습니다.', important=True)
                    self.app.processEvents()
                    packets_bottom = window.species_picker.mapTo(window, window.species_picker.rect().bottomLeft()).y()
                    plant_top = window.plant_button.mapTo(window, window.plant_button.rect().topLeft()).y()
                    self.assertLess(packets_bottom, plant_top)
                    window.notify('')
                    window.navigate(1)
                    window.pages.finish_transition()
                    self.app.processEvents()
                    viewport = window.pages.widget(SHOP_PAGE).findChild(QScrollArea).viewport()
                    for button in (*(button for button in window.shop_picker.buttons.values() if button.isVisible()), window.buy_seed_button):
                        self.assertTrue(button.isVisible())
                        detail = (side, button.text(), button.geometry(), viewport.rect())
                        self.assertTrue(viewport.rect().contains(
                            button.mapTo(viewport, button.rect().topLeft())), detail)
                        self.assertTrue(viewport.rect().contains(
                            button.mapTo(viewport, button.rect().bottomRight())), detail)
                    window.navigate(-1)
                    window.pages.finish_transition()
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
