"""High-grade routes: dice topology, guarantees, migration and saved UI transitions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from morning_bloom import gacha_board as board
from morning_bloom.app import Window
from morning_bloom.model import Garden
from morning_bloom.storage import Store, SaveError, migrate


def low_roll(n):
    return 0 if n == 6 else n - 1


class SideBoardRules(unittest.TestCase):
    def test_every_side_board_start_and_dice_pair(self):
        for gate in board.SIDE_BOARDS:
            for start in range(12):
                for a in range(1, 7):
                    for b in range(1, 7):
                        faces = iter((a - 1, b - 1))
                        state = board.initial_state()
                        state.update(position=gate, side_gate=gate, side_position=start)
                        result = board.simulate(state, 1, 10,
                            randbelow=lambda n: next(faces) if n == 6 else n - 1)
                        draw = result['results'][0]
                        path = [(start + i - 1) % 12 + 1 for i in range(1, a + b + 1)]
                        self.assertEqual(draw['path'], path)
                        self.assertEqual(draw['position'], path[-1])
                        self.assertEqual(draw['board_gate'], gate)
                        self.assertEqual(result['state']['position'], gate)
                        expected = 'SSR' if path[-1] in board.SIDE_BOARDS[gate]['ssr_cells'] else 'SR'
                        self.assertEqual(draw['rarity'], expected)
                        board.validate(result['state'])

    def test_enter_two_paid_draws_exit_and_resume_at_gate(self):
        for gate in board.SIDE_BOARDS:
            garden = Garden(100, sunlight=100)
            garden.gacha['tickets'] = 0
            garden.gacha['board']['position'] = gate - 2
            entry = garden.draw_gacha('pot', randbelow=low_roll)[0]
            self.assertIsNone(entry['board_gate'])
            for i in range(2):
                draw = garden.draw_gacha('pot', randbelow=low_roll)[0]
                self.assertEqual(draw['board_gate'], gate)
                self.assertIn(draw['rarity'], ('SR', 'SSR'))
                self.assertEqual(draw['exited'], i == 1)
                garden = Garden.from_dict(garden.to_dict())
            self.assertEqual(garden.sunlight, 70)
            self.assertEqual(garden.gacha['board']['position'], gate)
            self.assertIsNone(garden.gacha['board']['side_gate'])
            next_draw = garden.draw_gacha('pot', randbelow=low_roll)[0]
            self.assertIsNone(next_draw['board_gate'])
            self.assertEqual(next_draw['position'], (gate + 1) % 60 + 1)

    def test_categories_high_grade_pools_pity_and_no_nested_gates(self):
        for category in board.REWARDS:
            for gate in board.SIDE_BOARDS:
                garden = Garden(100, sunlight=100)
                garden.gacha['board'].update(position=gate, side_gate=gate, side_position=9, ssr_miss=59)
                results = garden.draw_gacha(category, 10, low_roll)
                self.assertEqual(results[0]['position'], 11)  # Side 11 is not another entrance.
                self.assertEqual(results[0]['side_gate'], gate)
                self.assertEqual(results[0]['rarity'], 'SSR')
                for draw in results[:2]:
                    self.assertIn(draw['item'], board.reward_pool(category, draw['rarity'], gate))
                    self.assertNotEqual(draw['rarity'], 'R')
                self.assertIsNone(results[2]['board_gate'])
                Garden.from_dict(garden.to_dict())

    def test_insufficient_payment_and_invalid_roll_are_atomic_on_side(self):
        state = board.initial_state()
        state.update(position=26, side_gate=26, side_position=11, side_step=1)
        original = deepcopy(state)
        with self.assertRaises(ValueError):
            board.simulate(state, 10, 99, randbelow=low_roll)
        with self.assertRaises(ValueError):
            board.simulate(state, 1, 10, randbelow=lambda n: n)
        self.assertEqual(state, original)

    def test_v15_migration_preserves_inventory_history_and_remaining_draws(self):
        for step in range(5):
            garden = Garden(100, sunlight=40)
            garden.draw_gacha('pot', randbelow=low_roll)
            old = garden.to_dict()
            old['schema'] = 15
            old.pop('pot_skins', None)
            old.pop('pot_colors')
            old.pop('flower_pots')
            state = old['gacha']['board']
            state.pop('side_position')
            state.update(position=17, side_gate=26, side_step=step)
            for record in old['gacha']['history']:
                record.pop('board_gate')
            original = deepcopy(old)
            updated = migrate(old)
            self.assertEqual(old, original)
            restored = Garden.from_dict(updated)
            self.assertEqual(restored.sunlight, old['sunlight'])
            self.assertEqual(restored.owned_skins, old['owned_skins'])
            self.assertEqual(updated['gacha']['history'][0]['board_gate'], None)
            new_state = restored.gacha['board']
            self.assertEqual(new_state['side_gate'], 26 if step < 2 else None)
            self.assertEqual(new_state['side_step'], step if step < 2 else 0)
            with tempfile.TemporaryDirectory() as tmp:
                store = Store(Path(tmp) / 'garden.json')
                store.path.write_text(json.dumps(old), encoding='utf-8')
                loaded = store.load(100)
                store.save(loaded)
                self.assertEqual(store.load(100).to_dict(), updated)
                self.assertTrue(store.migration_backup.exists())

    def test_side_probability_boundary_and_cloud_restore(self):
        for roll, expected in ((499, 'SSR'), (500, 'SR'), (9999, 'SR')):
            garden = Garden(100, sunlight=50)
            garden.gacha['board'].update(position=11, side_gate=11)
            rng = lambda n: 0 if n == 6 else roll if n == 10000 else 0
            result = garden.draw_gacha('garden', randbelow=rng)[0]
            self.assertEqual(result['rarity'], expected)
            with tempfile.TemporaryDirectory() as tmp:
                store = Store(Path(tmp) / 'garden.json')
                restored = store.replace_from_cloud(garden.to_dict(), 100)
                self.assertEqual(restored.to_dict(), garden.to_dict())

    def test_v16_two_draw_limit_migrates_local_and_cloud_without_changing_rewards(self):
        for gate in board.SIDE_BOARDS:
            for step in range(4):
                garden = Garden(100, sunlight=100)
                garden.draw_gacha('pot', randbelow=low_roll)
                old = garden.to_dict()
                old['schema'] = 16
                old.pop('pot_skins', None)
                old.pop('pot_colors')
                old.pop('flower_pots')
                old['gacha']['board'].update(position=gate, side_gate=gate,
                                             side_step=step, side_position=9)
                original = deepcopy(old)
                expected = deepcopy(old)
                expected['schema'] = Garden.CURRENT_SCHEMA
                expected['pot_skins'] = [expected['equipped_skin'] for _ in expected['pots']]
                expected['pot_colors'] = ['original' for _ in expected['pots']]
                expected['flower_pots'] = {}
                if step >= 2:
                    expected['gacha']['board'].update(side_gate=None, side_step=0, side_position=0)
                self.assertEqual(migrate(old), expected)
                self.assertEqual(old, original)
                with tempfile.TemporaryDirectory() as tmp:
                    store = Store(Path(tmp) / 'garden.json')
                    store.path.write_text(json.dumps(old), encoding='utf-8')
                    loaded = store.load(100)
                    self.assertEqual(loaded.to_dict(), expected)
                    store.save(loaded)
                    self.assertEqual(json.loads(store.migration_backup.read_text()), original)
                    self.assertEqual(store.replace_from_cloud(old, 100).to_dict(), expected)
                if step == 1:
                    draw = loaded.draw_gacha('pot', randbelow=low_roll)[0]
                    self.assertTrue(draw['exited'])
                    self.assertEqual(draw['board_gate'], gate)

    def test_v16_migration_rejects_corrupt_progress_and_current_schema_keeps_two_draw_limit(self):
        old = Garden(100).to_dict()
        old['schema'] = 16
        old.pop('pot_skins', None)
        old.pop('pot_colors')
        old.pop('flower_pots')
        old['gacha']['board'].update(position=26, side_gate=26, side_step=2)
        for field, invalid in (('side_step', 4), ('side_step', True), ('side_gate', 12),
                               ('side_position', 12), ('total', -1)):
            broken = deepcopy(old)
            broken['gacha']['board'][field] = invalid
            with self.assertRaises(ValueError):
                migrate(broken)
        broken = deepcopy(old)
        broken.pop('gacha')
        with self.assertRaises(ValueError):
            migrate(broken)
        old['schema'] = Garden.CURRENT_SCHEMA
        with self.assertRaises(ValueError):
            Garden.from_dict(old)

    def test_corrupt_legacy_markers_and_side_history_are_rejected(self):
        old = Garden(100).to_dict()
        old['schema'] = 15
        old.pop('pot_skins', None)
        old.pop('pot_colors')
        old.pop('flower_pots')
        old['gacha']['board'].pop('side_position')
        for field, invalid in (('position', 60), ('side_gate', 12), ('side_gate', []),
                               ('side_step', True), ('side_step', 5), ('total', -1)):
            broken = deepcopy(old)
            broken['gacha']['board'].update(side_gate=26, side_step=4)
            broken['gacha']['board'][field] = invalid
            with self.assertRaises(ValueError):
                migrate(broken)
        garden = Garden(100)
        garden.gacha['board'].update(position=56, side_gate=56)
        garden.draw_gacha('pot', randbelow=low_roll)
        for field, invalid in (('board_gate', 12), ('position', 13), ('rarity', 'R')):
            broken = garden.to_dict()
            broken['gacha']['history'][0][field] = invalid
            with self.assertRaises(ValueError):
                Garden.from_dict(broken)


class SideBoardUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_ten_draws_animate_entry_side_and_return_on_the_saved_boards(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(time.time(), sunlight=100)
            garden.gacha['board']['position'] = 9
            window = Window(store, garden, True)
            window._test_sunlight = False
            window.clock.stop()
            window.autosave.stop()
            window.open_gacha_board()
            dialog = window._gacha_board_window
            self.app.processEvents()
            with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=low_roll):
                dialog.draw(10)
            saved = deepcopy(garden.gacha)
            seen = []
            while dialog.animating:
                dialog.timer.stop()
                draw = dialog.current_result
                seen.append(draw['board_gate'])
                self.assertEqual(dialog._layout_gate, draw['board_gate'])
                self.assertEqual(sum(not c.isHidden() for c in dialog.cells.values()),
                                 12 if draw['board_gate'] else 60)
                dialog._start_movement()
                dialog.movement.setCurrentTime(dialog.movement.duration())
                self.assertIn(board.board_name(draw['board_gate']), dialog.result.text())
                dialog.timer.stop()
                dialog.animation_step()
            self.assertEqual(seen[:4], [None, 11, 11, None])
            self.assertEqual(garden.gacha, saved)
            self.assertEqual(store.load(garden.last_update).gacha, saved)
            dialog.close()
            window.close()

    def test_side_save_failure_close_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(time.time(), sunlight=100)
            garden.gacha['board'].update(position=56, side_gate=56, side_step=0, side_position=11)
            window = Window(store, garden, True)
            window._test_sunlight = False
            window.open_gacha_board()
            dialog = window._gacha_board_window
            before = deepcopy(garden.to_dict())
            with patch.object(store, 'save', side_effect=SaveError('full')):
                dialog.draw(1)
            self.assertFalse(dialog.animating)
            self.assertEqual(garden.gacha, before['gacha'])
            self.assertEqual(garden.sunlight, before['sunlight'])
            self.assertEqual(garden.owned_skins, before['owned_skins'])
            with patch('morning_bloom.gacha_board.secrets.randbelow', side_effect=low_roll):
                dialog.draw(1)
            saved = deepcopy(garden.gacha)
            dialog.timer.stop()
            dialog._start_movement()
            dialog.movement.pause()
            dialog.close()
            window.open_gacha_board()
            dialog = window._gacha_board_window
            self.assertEqual(dialog._layout_gate, 56)
            self.assertIn('황금 곁길', dialog.position_label.text())
            self.assertIn('1/2', dialog.gate_label.text())
            self.assertEqual(store.load(garden.last_update).gacha, saved)
            dialog.close()
            window.close()
