import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from morning_bloom.app import Window
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
            index = window.species_picker.findData('starflower')
            window.species_picker.setCurrentIndex(index)
            self.assertIn('3시간', window.species_picker.currentText())
            window.plant_button.click()
            window.water_button.click()
            window.mist_button.click()
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
            window.species_picker.setCurrentIndex(window.species_picker.findData('tulip'))
            window.plant_button.click()
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


if __name__ == '__main__':
    unittest.main()
