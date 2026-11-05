"""Eight rose colors, seed-only acquisition and honest, exact board probabilities."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QLabel

from legacy_fixture import v19_shape
from morning_bloom import gacha_board as board
from morning_bloom.app import Window
from morning_bloom.flower_art import paint_potted_flower
from morning_bloom.gacha_results import reward_item
from morning_bloom.model import Garden
from morning_bloom.plant_catalog import (PLANTS, ROSE_VARIETIES, ROSE_GACHA_PLANTS,
                                         SEED_PLANTS, SHOP_SEED_PLANTS, V19_SEED_PLANTS)
from morning_bloom.storage import SaveError, Store, migrate

NOW = 1_700_000_000


def force_draw(garden, tier, ticket):
    garden.gacha['board'] = board.initial_state()
    values = iter((0, 0, {'R': 9000, 'SR': 1000, 'SSR': 0}[tier], ticket))
    return garden.draw_gacha('rose', randbelow=lambda n: next(values))


class RoseRules(unittest.TestCase):
    def test_eight_variants_keep_red_id_and_shop_only_red_even_after_acquisition(self):
        self.assertEqual(list(ROSE_VARIETIES), ['rose', 'rose_pink', 'rose_orange', 'rose_white',
                                               'rose_yellow', 'rose_purple', 'rose_blue', 'rose_black'])
        garden = Garden(NOW, coins=10000, tutorial_used=True)
        self.assertTrue(garden.buy_seed('rose'))
        self.assertEqual(garden.coins, 9950)
        for key in ROSE_GACHA_PLANTS:
            garden.unlocked_plants.append(key)
            garden.seeds[key] = 1
            before = garden.to_dict()
            self.assertFalse(garden.buy_seed(key))
            self.assertEqual(garden.to_dict(), before)
        self.assertEqual(set(SHOP_SEED_PLANTS) & set(ROSE_VARIETIES), {'rose'})
        self.assertNotIn('rose', {key for pool in board.REWARDS['rose'].values() for key in pool})

    def test_ordinary_cell_probabilities_have_exact_configured_game_weights(self):
        expected = {'rose_pink': Fraction(25, 100), 'rose_white': Fraction(25, 100),
                    'rose_yellow': Fraction(20, 100), 'rose_orange': Fraction(15, 100),
                    'rose_purple': Fraction(10, 100), 'rose_black': Fraction(4, 100),
                    'rose_blue': Fraction(1, 100)}
        actual = {}
        for tier, pool in board.REWARDS['rose'].items():
            total = sum(board.reward_weight('rose', key) for key in pool)
            selected = [board.select_reward('rose', tier, None, lambda n, ticket=ticket: ticket)
                        for ticket in range(total)]
            counts = Counter(selected)
            self.assertEqual(set(counts), set(pool))
            for key, count in counts.items():
                actual[key] = Fraction({'R': 70, 'SR': 25, 'SSR': 5}[tier], 100) * Fraction(count, total)
        self.assertEqual(actual, expected)
        self.assertEqual(board.ordinary_item_probabilities('rose'), expected)
        self.assertEqual(sum(actual.values()), 1)
        self.assertEqual(board.item_rarity('plant', 'rose'), 'R')
        self.assertEqual(board.item_rarity('plant', 'rose_black'), 'SSR')
        self.assertEqual(board.item_rarity('plant', 'rose_blue'), 'SSR')

    def test_next_roll_probabilities_match_all_dice_and_rarity_buckets(self):
        states = []
        for position in (0, 9, 25, 48, 59):
            states.append({**board.initial_state(), 'position': position})
        states += [{**board.initial_state(), 'sr_miss': 9},
                   {**board.initial_state(), 'ssr_miss': 59}]
        states += [{**board.initial_state(), 'side_gate': gate, 'position': gate,
                    'side_position': 11, 'side_step': 1} for gate in board.SIDE_BOARDS]
        for state in states:
            before = deepcopy(state)
            observed = Counter()
            for first in range(6):
                for second in range(6):
                    for roll in range(0, 10000, 500):
                        values = iter((first, second, roll))
                        step = board._next(deepcopy(state), lambda n: next(values))
                        observed[step['rarity']] += 1
            expected = {tier: Fraction(observed[tier], 36 * 20) for tier in ('R', 'SR', 'SSR')}
            self.assertEqual(board.next_rarity_probabilities(state), expected, state)
            self.assertEqual(state, before)
            chances = board.item_probabilities('rose', state)
            self.assertEqual(sum(chances.values()), 1)
            if state['ssr_miss'] == 59 or state['side_gate'] == board.GOLD:
                self.assertEqual(chances['rose_blue'], Fraction(1, 5))
                self.assertEqual(chances['rose_black'], Fraction(4, 5))
                self.assertEqual(chances['rose_pink'], 0)

    def test_duplicate_roses_always_grant_a_seed_and_keep_weighted_item(self):
        garden = Garden(NOW, sunlight=100, tutorial_used=True)
        first = force_draw(garden, 'R', 0)[0]
        second = force_draw(garden, 'R', 0)[0]
        self.assertEqual(first['item'], 'rose_pink')
        self.assertFalse(first['duplicate'])
        self.assertTrue(second['duplicate'])
        self.assertEqual(garden.seed_count('rose_pink'), 2)
        self.assertEqual(second['leaves'], 2)
        self.assertTrue(garden.plant(NOW, 'rose_pink'))
        plant_id = garden.pot['plant_id']
        garden.care('water', NOW)
        garden.advance(NOW + PLANTS['rose_pink'].growth_seconds)
        self.assertTrue(garden.harvest(garden.last_update))
        self.assertEqual(garden.collection[-1]['species'], 'rose_pink')
        self.assertEqual(garden.collection[-1]['id'], plant_id)
        self.assertIn('rose_pink', garden.discovered_plants)
        self.assertEqual(garden.seed_count('rose_pink'), 1)
        Garden.from_dict(garden.to_dict())

    def test_each_rose_color_is_reachable_at_its_weight_interval(self):
        for tier, pool in board.REWARDS['rose'].items():
            start = 0
            for key in pool:
                for ticket in (start, start + board.reward_weight('rose', key) - 1):
                    garden = Garden(NOW, sunlight=100)
                    result = force_draw(garden, tier, ticket)[0]
                    self.assertEqual((result['item'], result['rarity']), (key, tier))
                    self.assertEqual(garden.seed_count(key), 1)
                    self.assertEqual(reward_item(result).name, PLANTS[key].name)
                start += board.reward_weight('rose', key)

    def test_bad_weighted_rng_leaves_seeds_money_and_history_unchanged(self):
        for invalid in (-1, True, 14):
            garden = Garden(NOW, sunlight=100)
            before = garden.to_dict()
            self.assertFalse(force_draw(garden, 'R', invalid))
            self.assertEqual(garden.to_dict(), before)

    def test_v19_migration_preserves_red_plants_ids_progress_and_custom_pots(self):
        garden = Garden(NOW, seeds={'rose': 4}, coins=900, tutorial_used=True,
                        owned_skins=['terracotta', 'sage'])
        garden.plant(NOW, 'rose')
        garden.care('water', NOW)
        garden.pot['growth'] = garden.pot['duration']
        garden.harvest(NOW)
        item_id = garden.collection[-1]['id']
        garden.set_plant_pot(item_id, 'sage', 'beige')
        garden.plant(NOW, 'rose')
        garden.care('water', NOW)
        garden.pot['growth'] = 1234
        garden.set_slot_pot(0, 'sage', 'charcoal')
        old = v19_shape(garden.to_dict())
        old['schema'] = 19
        before = deepcopy(old)
        upgraded = migrate(old)
        self.assertEqual(old, before)
        for key in old:
            if key not in ('schema', 'seeds'):
                self.assertEqual(upgraded[key], old[key], key)
        self.assertEqual({k: upgraded['seeds'][k] for k in V19_SEED_PLANTS}, old['seeds'])
        self.assertTrue(all(upgraded['seeds'][key] == 0 for key in ROSE_GACHA_PLANTS))
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            raw = json.dumps(old, ensure_ascii=False)
            store.path.write_text(raw, encoding='utf-8')
            loaded = store.load(NOW)
            store.save(loaded)
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            self.assertEqual(store.replace_from_cloud(old, NOW).to_dict(), upgraded)
            self.assertEqual(store.load(NOW).source_pot(item_id), dict(skin='sage', color='beige'))

    def test_v19_extra_or_negative_seed_values_are_never_silently_repaired(self):
        for seeds in ({**dict.fromkeys(V19_SEED_PLANTS, 0), 'rose_blue': 0},
                      {**dict.fromkeys(V19_SEED_PLANTS, 0), 'rose': -1}):
            old = v19_shape(Garden(NOW).to_dict())
            old.update(schema=19, seeds=seeds)
            with self.assertRaises(ValueError):
                migrate(old)


class RoseInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(NOW, sunlight=500, coins=500, tutorial_used=True,
                             tutorial_reward_claimed=True)
        self.clock = patch('morning_bloom.app.time.time', return_value=NOW)
        self.clock.start()
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        if self.window._gacha_board_window:
            self.window._gacha_board_window.done(0)
        self.window.close_collection_picker()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.clock.stop()
        self.temp.cleanup()

    def test_seed_shop_excludes_seven_roses_but_owned_planting_includes_them(self):
        self.assertIn('rose', self.window.shop_picker.buttons)
        self.assertFalse(set(ROSE_GACHA_PLANTS) & set(self.window.shop_picker.buttons))
        force_draw(self.garden, 'SSR', 0)
        self.window.refresh()
        self.assertEqual(self.garden.seed_count('rose_blue'), 1)
        self.assertIn('rose_blue', self.window.species_picker._available_keys)
        self.assertTrue(self.window.species_picker.buttons['rose_blue'].isEnabled())
        self.assertIn('SSR', self.window.species_picker.buttons['rose_blue'].toolTip())

    def test_ten_draw_summary_grants_exactly_ten_seeds_and_save_failure_rolls_back(self):
        self.window.open_gacha_board()
        dialog = self.window._gacha_board_window
        dialog.category.setCurrentIndex(dialog.category.findData('rose'))
        before = self.garden.to_dict()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            dialog.draw(10)
        self.assertEqual(self.garden.to_dict(), before)
        self.assertFalse(dialog.animating)
        self.assertIsNone(dialog.results_dialog)
        dialog.draw(10)
        self.assertEqual(sum(self.garden.seeds[key] for key in ROSE_GACHA_PLANTS), 10)
        saved = self.garden.to_dict()
        dialog.finish_animation()
        self.assertEqual(len(dialog.results_dialog.cards), 10)
        self.assertTrue(all('씨앗 +1' in card.accessibleName() for card in dialog.results_dialog.cards))
        dialog.finish_animation()
        self.assertEqual(self.garden.to_dict(), saved)
        self.assertEqual(self.store.load(NOW).to_dict(), saved)

    def test_probability_dialog_has_eight_rows_real_next_rates_and_no_save_effect(self):
        self.garden.gacha['board'].update(position=56, side_gate=56)
        self.window.open_gacha_board()
        dialog = self.window._gacha_board_window
        dialog.category.setCurrentIndex(dialog.category.findData('rose'))
        before = self.garden.to_dict()
        dialog.probabilities_button.click()
        rates = dialog.probabilities_dialog
        self.assertEqual(rates.table.rowCount(), 8)
        self.assertEqual(rates.table.item(0, 2).text(), '상점')
        self.assertEqual(rates.table.item(0, 3).text(), '0%')
        self.assertEqual(rates.table.item(6, 3).text(), '20%')
        self.assertEqual(rates.table.item(7, 3).text(), '80%')
        self.assertTrue(any('실측값이 아닌' in label.text() for label in rates.findChildren(QLabel)))
        for side in (320, 520):
            rates.resize(side, side)
            self.app.processEvents()
            self.assertTrue(rates.rect().contains(rates.table.geometry().bottomRight()))
            self.assertEqual(rates.table.horizontalScrollBar().maximum(), 0)
        rates.accept()
        self.assertEqual(self.garden.to_dict(), before)
        self.assertIsNone(dialog.probabilities_dialog)

    def test_all_eight_blooms_are_distinct_and_default_pot_override_is_retracted(self):
        images = []
        for key in ROSE_VARIETIES:
            image = QImage(380, 180, QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            paint_potted_flower(painter, PLANTS[key])
            painter.end()
            self.assertEqual(image.pixelColor(180, 150).name(), '#c98c67')
            images.append(image.copy(145, 0, 90, 75))
        self.assertEqual(len({bytes(image.bits()) for image in images}), 8)
        self.assertEqual(PLANTS['daisy'].pot_color, '#bd7e5c')
        self.assertEqual(set(SEED_PLANTS) - set(SHOP_SEED_PLANTS), set(ROSE_GACHA_PLANTS))


if __name__ == '__main__':
    unittest.main()
