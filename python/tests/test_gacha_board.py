"""Two-dice movement, persistent rewards, and board animation lifecycle checks."""
import unittest
import tempfile
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QAbstractAnimation, QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom import gacha_board as board
from morning_bloom.app import Window
from morning_bloom.model import FERTILIZER_CAP, FERTILIZER_LEAF_PRICE, Garden
from morning_bloom.storage import SaveError, Store, migrate


def low_roll(n):
    return 0 if n == 6 else n - 1


class FlowerBoardRules(unittest.TestCase):
    def test_price_and_failed_draw_are_atomic(self):
        state = board.initial_state()
        with self.assertRaises(ValueError):
            board.simulate(state, 10, 99, randbelow=low_roll)
        self.assertEqual(state, board.initial_state())
        result = board.simulate(state, 10, 100, randbelow=low_roll)
        self.assertEqual(result['sunlight'], 0)
        self.assertEqual(result['state']['position'], 20)
        self.assertEqual(len(result['results']), 10)
        self.assertEqual(state, board.initial_state())

    def test_free_tickets_take_priority_without_mixing(self):
        result = board.simulate(board.initial_state(), 1, 0, 1, low_roll)
        self.assertEqual((result['sunlight'], result['free_tickets']), (0, 0))
        with self.assertRaises(ValueError):
            board.simulate(board.initial_state(), 10, 90, 9, low_roll)

    def test_four_mid_side_guarantees_and_wrap(self):
        for target in (11, 26, 41, 56):
            state = board.initial_state()
            state['position'] = target - 2
            result = board.simulate(state, 1, 10, randbelow=low_roll)
            self.assertEqual(result['results'][0]['rarity'], 'SSR' if target == 56 else 'SR')
            self.assertEqual(result['results'][0]['side_gate'], target)
        state = board.initial_state()
        state['position'] = 59
        result = board.simulate(state, 10, 100, randbelow=low_roll)
        self.assertEqual([r['position'] for r in result['results']], list(range(1, 20, 2)))
        self.assertEqual(result['results'][0]['path'], [60, 1])
        self.assertEqual(result['state']['position'], 19)

    def test_pity_and_side_route(self):
        state = board.initial_state()
        state['position'] = 9
        first = board.simulate(state, 1, 10, randbelow=low_roll)
        self.assertEqual((first['results'][0]['side_gate'], first['results'][0]['side_step']), (11, 0))
        after = board.simulate(first['state'], 10, 100, randbelow=low_roll)
        self.assertEqual([r['side_step'] for r in after['results'][:4]], [1, 2, 3, 4])
        self.assertIsNone(after['results'][4]['side_gate'])
        state = board.initial_state()
        state.update(position=2, sr_miss=9, ssr_miss=59)
        result = board.simulate(state, 1, 10, randbelow=low_roll)
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
        self.assertEqual(restored.gacha['board']['position'], 0)
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
            with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=low_roll):
                dialog.draw(1)
            self.assertEqual(store.load(garden.last_update).gacha['board']['position'], 2)
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
        garden.gacha['board']['position'] = board.GOLD - 12
        result = garden.draw_gacha('pot', randbelow=lambda n: n - 1)
        self.assertEqual(result[0]['item'], 'rose')
        self.assertTrue(garden.equip_skin('rose'))
        restored = Garden.from_dict(garden.to_dict())
        self.assertEqual(restored.equipped_skin, 'rose')
        self.assertIn('rose', restored.owned_skins)
        # Existing v14 owners have no draw history proving the purchase route.
        old_owner = Garden(100, owned_skins=['terracotta', 'rose'], equipped_skin='rose')
        self.assertEqual(Garden.from_dict(old_owner.to_dict()).equipped_skin, 'rose')

    def test_all_dice_pairs_and_board_starts_preserve_ordered_path(self):
        totals = Counter()
        for a in range(1, 7):
            for b in range(1, 7):
                totals[a + b] += 1
                for start in range(board.LENGTH):
                    draws = iter([a - 1, b - 1])
                    rng = lambda n: next(draws) if n == 6 else n - 1
                    state = board.initial_state()
                    state['position'] = start
                    result = board.simulate(state, 1, 10, randbelow=rng)
                    step = result['results'][0]
                    self.assertEqual(step['dice'], [a, b])
                    self.assertEqual(step['distance'], a + b)
                    self.assertEqual(step['path'], [(start + i - 1) % 60 + 1 for i in range(1, a + b + 1)])
                    self.assertEqual(result['state']['position'], (start + a + b) % 60)
                    self.assertEqual(result['state']['total'], 1)
        self.assertEqual([totals[i] for i in range(2, 13)], [1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1])

    def test_passed_special_does_not_grant_a_second_or_forced_reward(self):
        state = board.initial_state()
        state['position'] = 10
        result = board.simulate(state, 1, 10, randbelow=low_roll)
        self.assertEqual(result['results'][0]['path'], [11, 12])
        self.assertEqual(result['results'][0]['rarity'], 'R')
        self.assertFalse(result['results'][0]['special'])
        self.assertEqual(result['state']['total'], 1)

    def test_invalid_dice_never_mutate_the_input(self):
        for invalid in (-1, 6, True, .5):
            state = board.initial_state()
            with self.assertRaises(ValueError):
                board.simulate(state, 1, 10, randbelow=lambda n: invalid)
            self.assertEqual(state, board.initial_state())

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


class DiceBoardInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(time.time(), sunlight=100)
        self.window = Window(self.store, self.garden, True)
        self.window.clock.stop()
        self.window.autosave.stop()
        self.window.open_gacha_board()
        self.dialog = self.window._gacha_board_window
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_until_idle(self):
        deadline = QElapsedTimer()
        deadline.start()
        while self.dialog.animating and deadline.elapsed() < 4000:
            QTest.qWait(10)
        self.assertFalse(self.dialog.animating)

    def test_dice_then_seed_movement_then_reveal_use_the_saved_result(self):
        dialog = self.dialog
        faces = iter([1, 4])  # 2 + 5; other random calls choose the lowest rarity.
        rng = lambda n: next(faces) if n == 6 else n - 1
        with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=rng):
            dialog.draw(1)
        saved = self.store.load(self.garden.last_update).gacha
        self.assertEqual(saved['board']['position'], 7)
        self.assertEqual(saved['tickets'], 2)
        self.assertEqual(dialog.phase, 'rolling')
        self.assertEqual(dialog.display_position, 0)
        self.assertEqual(dialog.history.count(), 0)
        dialog.draw(1)  # Rapid repeat input cannot charge or reroll.
        self.assertEqual(self.garden.gacha, saved)
        dialog.timer.stop()
        dialog._roll_frame = dialog.ROLL_FRAMES - 1
        dialog._tick()
        self.assertEqual([die.value for die in dialog.dice], [2, 5])
        self.assertIn('7칸', dialog.dice_total.text())
        dialog.timer.stop()
        dialog._start_movement()
        dialog.movement.pause()
        origin = dialog._cell_center(0)
        dialog.movement.setCurrentTime(dialog.movement.duration() // 2)
        self.assertNotEqual(dialog.seed.geometry().center(), origin.toPoint())
        self.assertEqual(dialog.display_position, 3)
        self.assertEqual(dialog.history.count(), 0)
        dialog.movement.resume()
        self.wait_until_idle()
        self.assertEqual(self.garden.gacha, saved)
        self.assertEqual(dialog.history.count(), 1)
        self.assertIn('7번 도착', dialog.result.text())
        self.assertLess((dialog.seed.geometry().center() - dialog._cell_center(7).toPoint()).manhattanLength(), 3)
        self.assertFalse(dialog.timer.isActive())
        self.assertEqual(dialog.movement.state(), QAbstractAnimation.Stopped)

    def test_ten_rolls_complete_naturally_with_one_payment(self):
        dialog = self.dialog
        dialog.ROLL_FRAMES = 1
        dialog.ROLL_TICK_MS = dialog.SETTLE_MS = dialog.PAUSE_MS = 1
        dialog.STEP_MS = 4
        with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=low_roll):
            dialog.draw(10)
        saved = self.store.load(self.garden.last_update).gacha
        self.assertEqual(self.garden.sunlight, 0)
        self.assertEqual(saved['board']['total'], 10)
        self.assertEqual(saved['board']['position'], 20)
        self.wait_until_idle()
        self.assertEqual(self.garden.gacha, saved)
        self.assertEqual(dialog.history.count(), 10)
        self.assertEqual([die.value for die in dialog.dice], [1, 1])

    def test_skip_and_close_stop_callbacks_without_losing_or_repeating_rewards(self):
        with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=low_roll):
            self.dialog.draw(10)
        saved = self.store.load(self.garden.last_update).gacha
        self.dialog.skip.click()
        self.assertFalse(self.dialog.animating)
        self.assertFalse(self.dialog.timer.isActive())
        self.assertEqual(self.dialog.history.count(), 10)
        self.assertEqual(self.dialog.movement.state(), QAbstractAnimation.Stopped)
        self.dialog.done(0)
        QTest.qWait(20)
        self.assertEqual(self.garden.gacha, saved)
        self.assertEqual(self.store.load(self.garden.last_update).gacha, saved)

    def test_close_during_seed_flight_and_reopen_uses_saved_destination(self):
        self.garden.gacha['board']['position'] = 59
        self.dialog.sync()
        with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=low_roll):
            self.dialog.draw(1)
        saved = self.store.load(self.garden.last_update).gacha
        self.dialog.timer.stop()
        self.dialog._start_movement()
        self.dialog.movement.pause()
        self.dialog.movement.setCurrentTime(self.dialog.STEP_MS)
        self.assertEqual(self.dialog.display_position, 60)
        self.assertIn('현재 60 / 60', self.dialog.position_label.text())
        self.dialog.resize(1080, 900)
        self.app.processEvents()
        self.dialog.done(0)
        self.assertFalse(self.dialog.timer.isActive())
        self.assertEqual(self.dialog.movement.state(), QAbstractAnimation.Stopped)
        self.window.open_gacha_board()
        self.dialog = self.window._gacha_board_window
        self.app.processEvents()
        self.assertIn('현재 1 / 60', self.dialog.position_label.text())
        self.assertEqual(self.garden.gacha, saved)

    def test_failed_save_does_not_start_the_dice_or_charge(self):
        before = self.garden.gacha.copy()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.dialog.draw(1)
        self.assertEqual(self.garden.gacha, before)
        self.assertFalse(self.dialog.animating)
        self.assertFalse(self.dialog.timer.isActive())
        self.assertEqual(self.dialog.movement.state(), QAbstractAnimation.Stopped)


if __name__ == '__main__':
    unittest.main()

