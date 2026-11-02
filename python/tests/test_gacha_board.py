"""Deterministic checks for the unreleased 60-space gacha rules."""
import unittest
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from morning_bloom import gacha_board as board
from morning_bloom.app import Window
from morning_bloom.model import FERTILIZER_CAP, FERTILIZER_LEAF_PRICE, Garden
from morning_bloom.storage import Store, migrate


class FlowerBoardRules(unittest.TestCase):
    def test_price_and_failed_draw_are_atomic(self):
        state = board.initial_state()
        with self.assertRaises(ValueError):
            board.simulate(state, 10, 99, randbelow=lambda n: 9999)
        self.assertEqual(state, board.initial_state())
        result = board.simulate(state, 10, 100, randbelow=lambda n: 9999)
        self.assertEqual(result['sunlight'], 0)
        self.assertEqual(result['state']['position'], 10)
        self.assertEqual(len(result['results']), 10)
        self.assertEqual(state, board.initial_state())

    def test_free_tickets_take_priority_without_mixing(self):
        result = board.simulate(board.initial_state(), 1, 0, 1, lambda n: 9999)
        self.assertEqual((result['sunlight'], result['free_tickets']), (0, 0))
        with self.assertRaises(ValueError):
            board.simulate(board.initial_state(), 10, 90, 9, lambda n: 9999)

    def test_four_mid_side_guarantees_and_wrap(self):
        for target in (11, 26, 41, 56):
            state = board.initial_state()
            state['position'] = target - 1
            result = board.simulate(state, 1, 10, randbelow=lambda n: 9999)
            self.assertEqual(result['results'][0]['rarity'], 'SSR' if target == 56 else 'SR')
            self.assertEqual(result['results'][0]['side_gate'], target)
        state = board.initial_state()
        state['position'] = 59
        result = board.simulate(state, 10, 100, randbelow=lambda n: 9999)
        self.assertEqual([r['position'] for r in result['results']], [60] + list(range(1, 10)))
        self.assertEqual(result['state']['position'], 9)

    def test_pity_and_side_route(self):
        state = board.initial_state()
        state['position'] = 10
        first = board.simulate(state, 1, 10, randbelow=lambda n: 9999)
        self.assertEqual((first['results'][0]['side_gate'], first['results'][0]['side_step']), (11, 0))
        after = board.simulate(first['state'], 10, 100, randbelow=lambda n: 9999)
        self.assertEqual([r['side_step'] for r in after['results'][:4]], [1, 2, 3, 4])
        self.assertIsNone(after['results'][4]['side_gate'])
        state = board.initial_state()
        state.update(position=2, sr_miss=9, ssr_miss=59)
        result = board.simulate(state, 1, 10, randbelow=lambda n: 9999)
        self.assertEqual(result['results'][0]['rarity'], 'SSR')
        self.assertEqual((result['state']['sr_miss'], result['state']['ssr_miss']), (0, 0))

    def test_validation_rejects_corrupt_state(self):
        state = board.initial_state()
        state['position'] = 60
        with self.assertRaises(ValueError):
            board.validate(state)

    def test_garden_draw_grants_existing_cosmetic_and_preserves_v13_save(self):
        garden = Garden(100)
        old = garden.to_dict()
        old.pop('gacha')
        old['schema'] = 13
        restored = Garden.from_dict(migrate(old))
        self.assertEqual(restored.sunlight, 0)
        self.assertEqual(restored.gacha['tickets'], 3)
        restored.sunlight = 100
        result = restored.draw_gacha('pot', 10, lambda n: n - 1)
        self.assertEqual(len(result), 10)
        self.assertEqual(restored.sunlight, 0)
        self.assertEqual(restored.gacha['board']['position'], 10)
        Garden.from_dict(restored.to_dict())

    def test_ui_board_opens_and_animates_saved_draw(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(time.time())
            window = Window(store, garden, True)
            window.open_gacha_board()
            dialog = window._gacha_board_window
            self.assertEqual(len(dialog.cells), 60)
            self.assertEqual(board.LENGTH, 60)
            dialog.draw(1)
            self.assertEqual(store.load(garden.last_update).gacha['board']['position'], 1)
            self.assertTrue(dialog.animating)
            self.assertFalse(dialog.one.isEnabled())
            dialog.finish_animation()
            self.assertFalse(dialog.animating)
            dialog.close()
            window.close()

    def test_rose_is_draw_only_and_existing_ownership_survives(self):
        garden = Garden(100, sunlight=1000)
        before = garden.to_dict()
        self.assertFalse(garden.buy_skin('rose'))
        self.assertEqual(garden.to_dict(), before)
        garden.gacha['tickets'] = 0
        garden.gacha['board']['position'] = board.GOLD - 1
        result = garden.draw_gacha('pot', randbelow=lambda n: n - 1)
        self.assertEqual(result[0]['item'], 'rose')
        self.assertTrue(garden.equip_skin('rose'))
        restored = Garden.from_dict(garden.to_dict())
        self.assertEqual(restored.equipped_skin, 'rose')
        self.assertIn('rose', restored.owned_skins)
        # Existing v14 owners have no draw history proving the purchase route.
        old_owner = Garden(100, owned_skins=['terracotta', 'rose'], equipped_skin='rose')
        self.assertEqual(Garden.from_dict(old_owner.to_dict()).equipped_skin, 'rose')

    def test_leaf_fertilizer_purchase_preserves_other_balances_and_roundtrips(self):
        garden = Garden(100, sunlight=45, fertilizer=4, reward_wait=120,
                        last_reward_id='previous-minigame', vacation=True)
        garden.gacha['leaves'] = FERTILIZER_LEAF_PRICE + 2
        before = garden.to_dict()
        self.assertTrue(garden.buy_fertilizer_with_leaves())
        expected = {**before, 'fertilizer': 5,
                    'gacha': {**before['gacha'], 'leaves': 2}}
        self.assertEqual(garden.to_dict(), expected)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.save(garden)
            self.assertEqual(store.load(100).to_dict(), expected)

    def test_leaf_purchase_rejects_insufficient_balance_and_full_stock(self):
        garden = Garden(100)
        garden.gacha['leaves'] = FERTILIZER_LEAF_PRICE - 1
        before = garden.to_dict()
        self.assertFalse(garden.buy_fertilizer_with_leaves())
        self.assertEqual(garden.to_dict(), before)
        garden.gacha['leaves'] = FERTILIZER_LEAF_PRICE * 10
        garden.fertilizer = FERTILIZER_CAP - 1
        self.assertTrue(garden.buy_fertilizer_with_leaves())
        before = garden.to_dict()
        self.assertFalse(garden.buy_fertilizer_with_leaves())
        self.assertEqual(garden.to_dict(), before)
        garden.fertilizer_reserve = 3
        before = garden.to_dict()
        self.assertFalse(garden.buy_fertilizer_with_leaves())
        self.assertEqual(garden.to_dict(), before)


if __name__ == '__main__':
    unittest.main()

