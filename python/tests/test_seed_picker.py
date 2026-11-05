import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from morning_bloom.app import POT_PAGE, Window
from morning_bloom.model import Garden
from morning_bloom.plant_catalog import GACHA_PLANTS, SEED_PLANTS, SHOP_SEED_PLANTS
from morning_bloom.seed_picker import SeedPicker
from morning_bloom.storage import SaveError, Store


NOW = 1_700_000_000


class OwnedSeedPicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def picker(self, shop=False):
        picker = SeedPicker(shop=shop)
        picker.resize(320, picker.height())
        picker.show()
        self.addCleanup(picker.close)
        return picker

    @staticmethod
    def visible(picker):
        return [key for key, button in picker.buttons.items() if button.isVisible()]

    def test_only_owned_regular_random_and_gacha_seeds_have_pages(self):
        picker = self.picker()
        owned = {'starflower': 1, 'rose': 2, 'lavender': 1, GACHA_PLANTS[-1]: 3, 'random': 2}
        picker.update_counts({'daisy': 0, **owned})
        first = self.visible(picker)
        self.assertEqual(len(first), 3)
        self.assertEqual(picker.selected, 'starflower')
        self.assertFalse(picker.previous.isEnabled())
        self.assertTrue(picker.next.isEnabled())
        picker.next.click()
        second = self.visible(picker)
        self.assertEqual(len(second), 2)
        self.assertEqual(set(first + second), set(owned))
        self.assertIn(picker.selected, second)
        self.assertFalse(picker.next.isEnabled())
        self.assertTrue(picker.previous.isEnabled())
        picker.previous.click()
        self.assertEqual(self.visible(picker), first)

    def test_depleted_selection_falls_back_then_handles_empty_and_restock(self):
        picker = self.picker()
        picker.update_counts({'starflower': 1, 'random': 1})
        picker.buttons['random'].click()
        self.assertEqual(picker.selected, 'random')
        picker.update_counts({'starflower': 2})
        self.assertEqual(picker.selected, 'starflower')
        self.assertEqual(self.visible(picker), ['starflower'])
        picker.update_counts({})
        self.assertEqual(self.visible(picker), [])
        self.assertIsNone(picker.selected)
        self.assertTrue(picker.empty_state.isVisible())
        self.assertFalse(picker.next.isEnabled())
        self.assertFalse(picker.previous.isEnabled())
        picker.change_page(1)
        picker.change_page(-1)
        self.assertIsNone(picker.selected)
        picker.update_counts({'random': 1})
        self.assertEqual(self.visible(picker), ['random'])
        self.assertEqual(picker.selected, 'random')
        self.assertFalse(picker.empty_state.isVisible())

    def test_refresh_preserves_owned_selection_when_earlier_seeds_change(self):
        picker = self.picker()
        picker.update_counts(dict.fromkeys(SEED_PLANTS, 1))
        picker.next.click()
        selected = picker.selected
        picker.update_counts({selected: 4, 'random': 1})
        self.assertEqual(picker.selected, selected)
        self.assertEqual(set(self.visible(picker)), {selected, 'random'})
        picker.update_counts({selected: 5, 'random': 2, 'daisy': 1})
        self.assertEqual(picker.selected, selected)
        self.assertIn(selected, self.visible(picker))
        self.assertIn('5개', picker.buttons[selected].text())

    def test_shop_keeps_every_seed_available_to_browse_at_zero_stock(self):
        picker = self.picker(shop=True)
        picker.update_counts({})
        seen = set()
        while True:
            visible = self.visible(picker)
            self.assertTrue(visible)
            self.assertIn(picker.selected, visible)
            seen.update(visible)
            if not picker.next.isEnabled():
                break
            picker.next.click()
        self.assertEqual(seen, {*SHOP_SEED_PLANTS, 'random'})
        self.assertFalse(picker.empty_state.isVisible())

    def test_empty_inventory_purchase_consumption_and_save_failure_refresh_ui(self):
        with tempfile.TemporaryDirectory() as tmp, patch('morning_bloom.app.time.time', return_value=NOW):
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(NOW, seeds={}, coins=200, tutorial_used=True, tutorial_reward_claimed=True)
            self.assertFalse(any(garden.seeds.values()))
            window = Window(store, garden)
            window.show()
            self.app.processEvents()
            try:
                self.assertIsNone(window.species_picker.selected)
                self.assertFalse(window.plant_button.isEnabled())
                self.assertTrue(window.species_picker.empty_state.isVisible())
                self.assertIn('상점', window.plant_button.text())
                self.assertTrue(window.act(lambda: garden.buy_seed('starflower')))
                self.assertEqual(window.species_picker.selected, 'starflower')
                self.assertEqual(self.visible(window.species_picker), ['starflower'])
                self.assertTrue(window.plant_button.isEnabled())
                self.assertIn('별꽃', window.plant_button.text())
                with patch.object(store, 'save', side_effect=SaveError('disk full')):
                    window.plant_button.click()
                self.assertFalse(garden.planted)
                self.assertEqual(garden.seed_count('starflower'), 1)
                self.assertEqual(self.visible(window.species_picker), ['starflower'])
                self.assertTrue(window.plant_button.isEnabled())
                window.plant_button.click()
                self.assertTrue(garden.planted)
                self.assertEqual(garden.seed_count('starflower'), 0)
                self.assertIsNone(window.species_picker.selected)
                self.assertEqual(store.load(NOW).pot['species'], 'starflower')
                self.assertTrue(window.act(garden.buy_pot))
                self.assertTrue(window.navigate_pot(1))
                window.pot_slides.finish_transition()
                self.app.processEvents()
                self.assertEqual(window.pages.currentIndex(), POT_PAGE)
                self.assertEqual(self.visible(window.species_picker), [])
                self.assertTrue(window.species_picker.empty_state.isVisible())
                self.assertFalse(window.plant_button.isEnabled())
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
