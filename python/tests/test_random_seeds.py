"""Mystery-seed coverage, exact rates, persistence and shop disclosure."""
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel

from morning_bloom import gacha_board
from morning_bloom.app import SHOP_PAGE, Window
from morning_bloom.model import Garden
from morning_bloom.plant_catalog import (
    PLANTS, GACHA_PLANTS, ROSE_GACHA_PLANTS, MYSTERY_SEED_RARITIES,
    MYSTERY_SEED_PROBABILITIES, MYSTERY_SEED_TIER_PROBABILITIES,
    MYSTERY_SEED_TICKETS, MYSTERY_SEED_WEIGHTS, roll_mystery_seed,
)
from morning_bloom.storage import Store, migrate

NOW = 1_700_000_000


class MysterySeedRules(unittest.TestCase):
    def test_every_non_dandelion_plant_has_positive_odds_and_a_consistent_tier(self):
        self.assertEqual(set(MYSTERY_SEED_RARITIES), set(PLANTS) - {'dandelion'})
        self.assertEqual(set(MYSTERY_SEED_PROBABILITIES), set(MYSTERY_SEED_RARITIES))
        self.assertEqual(sum(MYSTERY_SEED_PROBABILITIES.values()), 1)
        self.assertTrue(all(rate > 0 for rate in MYSTERY_SEED_PROBABILITIES.values()))
        expected_tier_counts = {'R': 12, 'SR': 10, 'SSR': 6}
        for tier, chance in {'R': Fraction(7, 10), 'SR': Fraction(1, 4), 'SSR': Fraction(1, 20)}.items():
            keys = [key for key, rarity in MYSTERY_SEED_RARITIES.items() if rarity == tier]
            self.assertEqual(len(keys), expected_tier_counts[tier])
            self.assertEqual(sum(MYSTERY_SEED_PROBABILITIES[key] for key in keys), chance)
            self.assertEqual(MYSTERY_SEED_TIER_PROBABILITIES[tier], chance)
        self.assertEqual(MYSTERY_SEED_PROBABILITIES['ancient'], Fraction(1, 1000))
        for category in ('plant', 'rose'):
            for tier, pool in gacha_board.REWARDS[category].items():
                for key in pool:
                    self.assertEqual(MYSTERY_SEED_RARITIES[key], tier)

    def test_all_ticket_boundaries_and_invalid_draws(self):
        start = 0
        for key, weight in MYSTERY_SEED_WEIGHTS.items():
            for ticket in (start, start + weight - 1):
                self.assertEqual(roll_mystery_seed(lambda n: ticket), key)
            start += weight
        self.assertEqual(start, MYSTERY_SEED_TICKETS)
        for ticket in (-1, MYSTERY_SEED_TICKETS, True, 1.5, None):
            with self.subTest(ticket=ticket), self.assertRaises(ValueError):
                roll_mystery_seed(lambda n: ticket)

    def test_all_28_results_persist_grow_discover_and_sell_without_shop_unlock(self):
        ticket = 0
        for key, weight in MYSTERY_SEED_WEIGHTS.items():
            with self.subTest(species=key), tempfile.TemporaryDirectory() as tmp:
                store = Store(Path(tmp) / 'garden.json')
                garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True)
                with patch('morning_bloom.model.secrets.randbelow', return_value=ticket) as draw:
                    self.assertTrue(garden.buy_seed('random'))
                    draw.assert_called_once_with(MYSTERY_SEED_TICKETS)
                self.assertEqual(garden.coins, 100)
                self.assertEqual(garden.mystery_seeds, [key])
                self.assertEqual(garden.unlocked_plants, [])
                self.assertNotIn(key, garden.discovered_plants)
                store.save(garden)
                garden = store.load(NOW)
                with patch('morning_bloom.model.secrets.randbelow', side_effect=AssertionError('reroll')):
                    self.assertTrue(garden.plant(NOW, 'random'))
                self.assertEqual(garden.species, key)
                self.assertTrue(garden.mystery_hidden)
                self.assertEqual(garden.display_name, '신비한 식물')
                self.assertEqual(garden.duration, PLANTS[key].growth_seconds)
                store.save(garden)
                garden = store.load(NOW)
                self.assertEqual(garden.species, key)
                self.assertTrue(garden.mystery_hidden)
                self.assertTrue(garden.care('water', NOW))
                garden.growth = garden.duration
                self.assertFalse(garden.mystery_hidden)
                self.assertTrue(garden.harvest(NOW))
                store.save(garden)
                garden = store.load(NOW)
                self.assertEqual(garden.collection[0]['species'], key)
                self.assertIn(key, garden.discovered_plants)
                self.assertEqual(garden.unlocked_plants, [])
                if key in GACHA_PLANTS:
                    self.assertFalse(garden.buy_seed(key))
                self.assertTrue(garden.sell())
                self.assertEqual(garden.coins, 100 + PLANTS[key].sale_price)
            ticket += weight

    def test_existing_mystery_results_and_active_plants_are_not_rerolled(self):
        garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True,
                        mystery_seeds=['starflower', 'daisy', 'tulip', 'ancient'])
        self.assertTrue(garden.plant(NOW, 'random'))
        before = garden.to_dict()
        with patch('morning_bloom.model.secrets.randbelow', side_effect=AssertionError('reroll')):
            self.assertEqual(migrate(before), before)
            self.assertEqual(Garden.from_dict(before).to_dict(), before)


class MysterySeedInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shop_dialog_lists_all_rates_without_revealing_or_changing_saved_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(NOW, tutorial_used=True, tutorial_reward_claimed=True,
                            mystery_seeds=['rose_blue'])
            window = Window(store, garden)
            window.now = lambda: NOW
            try:
                window.show()
                window.pages.setCurrentIndex(SHOP_PAGE)
                window.shop_picker.buttons['random'].click()
                self.assertFalse(window.random_seed_probabilities_button.isHidden())
                self.assertIn('28종', window.shop_info.text())
                self.assertNotIn('33.3%', window.shop_info.text())
                before = garden.to_dict()
                window.random_seed_probabilities_button.click()
                dialog = window._random_seed_dialog
                self.assertIsNotNone(dialog)
                self.assertEqual(dialog.table.rowCount(), 28)
                rows = {dialog.table.item(row, 0).text(): row for row in range(28)}
                self.assertNotIn('민들레', rows)
                self.assertEqual(dialog.table.item(rows['고대 꽃'], 2).text(), '0.1%')
                self.assertEqual(dialog.table.item(rows['파랑 장미'], 2).text(), '0.98%')
                self.assertTrue(any('SSR 5%' in label.text() for label in dialog.findChildren(QLabel)))
                self.assertEqual(garden.to_dict(), before)
                window.open_random_seed_probabilities()
                self.assertIs(window._random_seed_dialog, dialog)
                dialog.accept()
                self.assertIsNone(window._random_seed_dialog)
                window.shop_picker.buttons['daisy'].click()
                self.assertTrue(window.random_seed_probabilities_button.isHidden())
            finally:
                window.clock.stop()
                window.autosave.stop()
                window.hide()
                window.deleteLater()
                self.app.processEvents()
