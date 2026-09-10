import tempfile
import time
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from morning_bloom.app import Window
from morning_bloom.model import Garden
from morning_bloom.storage import Store

class UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_click_loop_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            window = Window(store, Garden(time.time()), True)
            window.show()
            self.app.processEvents()
            self.assertEqual(window.width(), window.height())
            self.assertGreaterEqual(window.width(), 320)
            self.assertLessEqual(window.width(), 520)
            window.plant_button.click()
            window.water_button.click()
            self.assertTrue(window.garden.planted)
            window.offset = 61
            window.refresh()
            self.assertTrue(window.harvest_button.isEnabled())
            window.harvest_button.click()
            window.sell_button.click()
            self.assertEqual(window.garden.coins, 170)
            window.close()
            self.assertEqual(store.load(time.time()).coins, 170)

    def test_tulip_can_be_selected_and_planted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(
                time.time(),
                tutorial_used=True,
                seeds={'daisy': 0, 'tulip': 1},
            )
            window = Window(store, garden, True)
            tulip_index = window.species_picker.findData('tulip')
            window.species_picker.setCurrentIndex(tulip_index)
            window.plant_button.click()
            self.assertEqual(garden.species, 'tulip')
            self.assertIn('튤립', window.remaining.text())
            window.close()
