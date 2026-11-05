"""Issue 20-23 regressions through the actual widgets and save transactions."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from morning_bloom.app import Window
from morning_bloom.cosmetics import POT_SKINS
from morning_bloom.gacha_results import GachaResults
from morning_bloom.model import Garden
from morning_bloom.storage import SaveError, Store, migrate

NOW = 1_700_000_000


class FakeCloud:
    configured = connected = auto_retry_allowed = True
    email = 'test@example.invalid'
    def __init__(self, remote=None):
        self.remote, self.uploads, self.reads = remote, [], 0
    def download_save(self):
        self.reads += 1
        return deepcopy(self.remote)
    def upload_save(self, snapshot):
        self.uploads.append(deepcopy(snapshot))
        self.remote = dict(schema=1, saved_at=NOW, save=deepcopy(snapshot))
        return NOW


class ReleaseFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clock = patch('morning_bloom.app.time.time', return_value=NOW)
        self.clock.start()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = Garden(NOW, coins=500, sunlight=500, seeds={'daisy': 3, 'starflower': 3},
                             tutorial_used=True, tutorial_reward_claimed=True,
                             owned_skins=['terracotta', 'ivory', 'sage'], owned_themes=['grass', 'sky'])
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        self.window.cloud = None
        if self.window._gacha_board_window:
            self.window._gacha_board_window.done(0)
        self.window.close_collection_picker()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.clock.stop()
        self.temp.cleanup()

    def immediate(self, action, done, message, silent_error=False):
        done(action())
        return True

    def baseline(self):
        original = self.garden.to_dict()
        self.cloud = self.window.cloud = FakeCloud(dict(schema=1, saved_at=NOW, save=original))
        self.window._after_cloud_backup(NOW, self.window._cloud_digest(original), True)

    def test_startup_retains_and_uploads_unsynced_local_after_crash_without_pending(self):
        self.baseline()
        self.garden.coins = 700
        self.window.persist()
        self.window._cloud_pending_path().unlink()
        with patch.object(self.window, '_run_cloud', side_effect=self.immediate), \
                patch('morning_bloom.app.QMessageBox.question', side_effect=AssertionError('unexpected prompt')):
            self.window.startup_cloud_sync()
        self.assertEqual(self.garden.coins, 700)
        self.assertEqual(self.cloud.remote['save']['coins'], 700)
        self.assertFalse(self.window._cloud_pending_path().exists())

    def test_unknown_startup_requires_choice_and_cancel_preserves_both_saves(self):
        self.baseline()
        self.window._reset_cloud_state()
        self.garden.coins = 700
        with patch.object(self.window, '_run_cloud', side_effect=self.immediate), \
                patch('morning_bloom.app.QMessageBox.question', return_value=QMessageBox.Cancel) as prompt:
            self.window.startup_cloud_sync()
        prompt.assert_called_once()
        self.assertEqual((self.garden.coins, self.cloud.remote['save']['coins']), (700, 500))
        self.assertEqual(self.cloud.uploads, [])

    def test_exit_checks_conflict_and_cancellation_keeps_game_open(self):
        self.baseline()
        self.garden.coins = 700
        self.cloud.remote['save']['coins'] = 900
        with patch.object(self.window, '_run_cloud', side_effect=self.immediate), \
                patch('morning_bloom.app.QMessageBox.question', return_value=QMessageBox.Cancel) as prompt:
            self.window.close()
        self.assertEqual(self.cloud.reads, 1)
        prompt.assert_called_once()
        self.assertEqual(self.cloud.uploads, [])
        self.assertFalse(self.window._closing)
        self.assertEqual(self.store.load(NOW).coins, 700)
        self.assertEqual(self.cloud.remote['save']['coins'], 900)

    def test_multiple_remote_heads_can_restore_any_candidate_then_resolve(self):
        self.baseline()
        first = deepcopy(self.cloud.remote)
        first['save']['coins'] = 900
        second = deepcopy(first)
        second['save']['coins'] = 1234
        self.cloud.remote = {**first, 'alternatives': [second]}
        def choose(parent, title, text, labels, index, editable):
            return labels[2], True
        with patch.object(self.window, '_run_cloud', side_effect=self.immediate), \
                patch('morning_bloom.app.QInputDialog.getItem', side_effect=choose):
            self.window.auto_backup_cloud()
        self.assertEqual(self.garden.coins, 1234)
        self.assertEqual(self.cloud.uploads[-1]['coins'], 1234)
        self.assertEqual(self.store.load(NOW).coins, 1234)

    def test_clock_only_change_does_not_upload_again(self):
        self.baseline()
        self.cloud.remote['save']['last_update'] = NOW - 1
        with patch.object(self.window, '_run_cloud', side_effect=self.immediate):
            self.window.auto_backup_cloud()
        self.assertEqual(self.cloud.uploads, [])

    def test_garden_selection_is_owned_first_gray_locked_and_transactional(self):
        self.window.garden_style_button.click()
        dialog = self.window._cosmetic_dialog
        self.assertEqual(dialog.ordered_keys[:2], ['grass', 'sky'])
        self.assertTrue(dialog.buttons['cream'].icon().pixmap(80, 60).toImage().isGrayscale())
        before = self.garden.to_dict()
        dialog.select('cream')
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.apply()
        self.assertEqual(self.garden.to_dict(), before)
        dialog.select('sky')
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            dialog.apply()
        self.assertEqual(self.garden.equipped_theme, 'grass')
        dialog.apply()
        self.assertEqual(self.store.load(NOW).equipped_theme, 'sky')
        self.assertEqual(self.garden.sunlight, before['sunlight'])

    def choose_pot(self, key, cancel=False):
        self.window.pot_style_button.click()
        dialog = self.window._cosmetic_dialog
        dialog.select(key)
        dialog.reject() if cancel else dialog.apply()

    def test_cosmetic_grid_stays_scrollable_after_resizing_without_overlapping_cards(self):
        self.window.pot_style_button.click()
        dialog = self.window._cosmetic_dialog
        for side, columns in ((320, 2), (520, 3), (320, 2)):
            dialog.resize(side, side)
            self.app.processEvents()
            buttons = [dialog.buttons[key] for key in dialog.ordered_keys]
            self.assertGreater(dialog.scroll.verticalScrollBar().maximum(), 0)
            self.assertLess(buttons[0].geometry().bottom(), buttons[columns].geometry().top())
            self.assertTrue(dialog.rect().contains(dialog.apply_button.geometry().bottomRight()))
            self.assertEqual(len([b for b in dialog.content.children()
                                  if hasattr(b, 'isVisible') and b.isVisible()]), len(dialog.buttons))

    def test_planting_uses_independent_slot_skins_and_cancel_never_consumes_seed(self):
        self.assertTrue(self.window.act(self.garden.buy_pot))
        self.choose_pot('ivory')
        self.assertEqual(self.garden.pot_skins, ['ivory', 'terracotta'])
        self.window.plant_button.click()
        self.assertEqual(self.garden.pot_skins, ['ivory', 'terracotta'])
        self.window.navigate_pot(1)
        self.window.pot_slides.finish_transition()
        before = self.garden.to_dict()
        self.choose_pot('sage', cancel=True)
        self.assertEqual(self.garden.to_dict(), before)
        self.choose_pot('sage')
        before = self.garden.to_dict()
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.window.plant_button.click()
        self.assertEqual(self.garden.to_dict(), before)
        self.window.plant_button.click()
        self.assertEqual(self.store.load(NOW).pot_skins, ['ivory', 'sage'])
        self.assertEqual(self.garden.source_skin(self.garden.pots[0]['plant_id']), 'ivory')
        restored = self.store.replace_from_cloud(self.garden.to_dict(), NOW)
        self.assertEqual(restored.pot_skins, ['ivory', 'sage'])

    def test_v17_migration_preserves_everything_and_old_skin_for_each_slot(self):
        self.garden.buy_pot()
        self.garden.equip_skin('ivory')
        old = self.garden.to_dict()
        old.pop('pot_skins')
        old.pop('pot_colors')
        old.pop('flower_pots')
        old['schema'] = 17
        original = deepcopy(old)
        upgraded = migrate(old)
        self.assertEqual(old, original)
        self.assertEqual(upgraded['pot_skins'], ['ivory', 'ivory'])
        self.assertEqual({k: v for k, v in upgraded.items() if k not in ('schema', 'pot_skins', 'pot_colors', 'flower_pots')},
                         {k: v for k, v in old.items() if k != 'schema'})
        for invalid in ([], ['sage'], ['terracotta', 'rose']):
            broken = deepcopy(upgraded)
            broken['pot_skins'] = invalid
            with self.assertRaises(ValueError):
                Garden.from_dict(broken)

    def test_batch_summary_skip_has_exact_results_and_never_grants_twice(self):
        self.window.open_gacha_board()
        board = self.window._gacha_board_window
        board.category.setCurrentIndex(0)
        board.draw(10)
        expected = deepcopy(board.batch_results)
        self.assertEqual(len(expected), 10)
        committed = self.garden.to_dict()
        board.finish_animation()
        summary = board.results_dialog
        self.assertEqual(summary.results, expected)
        self.assertEqual(len(summary.cards), 10)
        self.assertEqual(summary.leaves, sum(item['leaves'] for item in expected))
        board.finish_animation()
        self.assertIs(board.results_dialog, summary)
        self.assertEqual(self.garden.to_dict(), committed)
        summary.accept()
        self.app.processEvents()
        board.draw(1)
        board.finish_animation()
        self.assertEqual(len(board.results_dialog.cards), 1)
        self.assertEqual(self.store.load(NOW).gacha, self.garden.gacha)

    def test_failed_draw_has_no_success_summary_and_ssr_reveal_uses_saved_item(self):
        self.window.open_gacha_board()
        board = self.window._gacha_board_window
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            board.draw(10)
        self.assertFalse(board.animating)
        self.assertIsNone(board.results_dialog)
        self.garden.gacha['board'].update(position=56, side_gate=56)
        board.draw(1)
        result = board.batch_results[0]
        self.assertEqual(result['rarity'], 'SSR')
        duration = board.reward_reveal.reveal(result)
        self.assertEqual(duration, 1000)
        self.assertIn('SSR', board.reward_reveal.accessibleName())
        self.assertFalse(board.reward_reveal.grab().isNull())
        board.finish_animation()
        self.assertEqual(board.results_dialog.results[0], result)


if __name__ == '__main__':
    unittest.main()
