import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morning_bloom.app import Window
from morning_bloom.model import (
    FERTILIZER_CAP, Garden, HOUR, MIST_INTERVAL, POT_PRICES,
    REWARD_INTERVAL, TYCOON_POT_DEFAULTS, TYCOON_RULE, WATER_INTERVAL,
)
from morning_bloom.storage import SaveError, Store, migrate

NOW = 1_700_000_000


def growing(species='starflower', now=NOW):
    garden = Garden(now, tutorial_used=True, tutorial_reward_claimed=True,
                    seeds={key: int(key == species) for key in ('daisy', 'starflower', 'tulip')})
    assert garden.plant(now, species)
    assert garden.care('water', now)
    return garden


def v5_data(garden):
    data = garden.to_dict()
    for key in ('fertilizer', 'reward_wait', 'last_reward_id'):
        data.pop(key)
    for pot in data['pots']:
        for key in TYCOON_POT_DEFAULTS:
            pot.pop(key)
        if pot['planted']:
            pot['ruleset_id'] = 'v0.4'
            pot['care_profile'] = 'tulip_midwater' if pot['species'] == 'tulip' else 'start_only'
    data['schema'] = 5
    return data


class TycoonRules(unittest.TestCase):
    def test_four_pots_have_sequential_prices_and_persist_selection(self):
        garden = Garden(NOW, coins=1000)
        for count, price in enumerate(POT_PRICES[1:], 2):
            before = garden.coins
            self.assertEqual(garden.next_pot_price, price)
            self.assertTrue(garden.buy_pot())
            self.assertEqual((len(garden.pots), garden.coins), (count, before - price))
        self.assertFalse(garden.buy_pot())
        self.assertIsNone(garden.next_pot_price)
        self.assertTrue(garden.select(3))
        self.assertEqual(Garden.from_dict(garden.to_dict()).selected, 3)

    def test_repeat_care_boundaries_and_bonus_only_once(self):
        garden = growing()
        self.assertEqual(garden.growth, 0)
        self.assertTrue(garden.care('mist', NOW))
        self.assertEqual(garden.growth, 60)
        self.assertFalse(garden.care('mist', NOW + MIST_INTERVAL - 1))
        self.assertTrue(garden.care('mist', NOW + MIST_INTERVAL))
        self.assertFalse(garden.care('water', NOW + WATER_INTERVAL - 1))
        self.assertTrue(garden.care('water', NOW + WATER_INTERVAL))
        self.assertEqual(garden.growth, WATER_INTERVAL + 120 + 180)
        self.assertEqual((garden.pot['mist_count'], garden.pot['water_count']), (2, 2))
        garden.advance(NOW + 3 * HOUR)
        self.assertTrue(garden.harvest(NOW + 3 * HOUR))
        self.assertEqual(garden.collection[0]['bonus_g'], 1)

    def test_offline_readiness_is_one_use_and_pot_clocks_are_independent(self):
        garden = growing('daisy')
        garden.coins = 1000
        garden.buy_pot()
        garden.select(1)
        garden.seeds['daisy'] = 1
        garden.plant(NOW + 600, 'daisy')
        garden.care('water', NOW + 600)
        garden.select(0)
        garden.advance(NOW + 1800)
        self.assertTrue(garden.can_care('water'))
        garden.select(1)
        self.assertFalse(garden.can_care('water'))
        garden.advance(NOW + 3600)
        self.assertTrue(garden.care('water', NOW + 3600))
        self.assertFalse(garden.care('water', NOW + 3600))
        self.assertEqual(garden.pots[0]['water_wait'], 0)
        self.assertEqual(garden.pots[1]['water_wait'], WATER_INTERVAL)

    def test_tulip_has_no_neglect_penalty_under_new_rules(self):
        garden = growing('tulip')
        garden.advance(NOW + 48 * HOUR)
        self.assertTrue(garden.bloomed)

    def test_tutorial_only_first_water_then_unlocks_items(self):
        garden = Garden(NOW, fertilizer=1)
        self.assertFalse(garden.reward_fertilizer('before', NOW))
        garden.plant(NOW)
        self.assertFalse(garden.use_fertilizer(NOW))
        garden.care('water', NOW)
        self.assertFalse(garden.care('mist', NOW))
        self.assertFalse(garden.care('water', NOW))
        self.assertFalse(garden.use_fertilizer(NOW))
        self.assertTrue(garden.harvest(NOW + 60))
        self.assertTrue(garden.can_reward_fertilizer)

    def test_fertilizer_only_changes_selected_growth_and_inventory(self):
        garden = growing()
        garden.coins = 200
        garden.buy_pot()
        garden.fertilizer = 2
        garden.care('mist', NOW)
        garden.reward_fertilizer('reward', NOW)
        before = garden.to_dict()
        self.assertTrue(garden.use_fertilizer(NOW))
        after = garden.to_dict()
        self.assertEqual(after['pots'][0]['growth'], before['pots'][0]['growth'] + 600)
        self.assertEqual(after['fertilizer'], before['fertilizer'] - 1)
        for key in ('last_update', 'reward_wait', 'sun_elapsed', 'sun_tokens', 'last_reward_id'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after['pots'][1], before['pots'][1])
        for key in ('water_wait', 'mist_wait', 'care_elapsed'):
            self.assertEqual(after['pots'][0][key], before['pots'][0][key], key)

    def test_fertilizer_caps_and_short_remaining_bloom(self):
        for species, limit in (('starflower', 4), ('daisy', 36), ('tulip', 72)):
            garden = growing(species)
            self.assertEqual(garden.pot['fertilizer_limit'], limit)
        garden = growing()
        garden.fertilizer = 10
        for _ in range(4):
            self.assertTrue(garden.use_fertilizer(NOW))
        self.assertFalse(garden.use_fertilizer(NOW))
        self.assertEqual(garden.fertilizer, 6)
        garden = growing()
        garden.fertilizer = 1
        garden.growth = garden.duration - 7 * 60
        self.assertTrue(garden.use_fertilizer(NOW))
        self.assertTrue(garden.bloomed)
        self.assertFalse(garden.use_fertilizer(NOW))
        self.assertFalse(garden.care('mist', NOW))

    def test_reward_cap_cooldown_duplicate_and_offline_no_auto_reward(self):
        garden = growing()
        self.assertTrue(garden.reward_fertilizer('one', NOW))
        self.assertFalse(garden.reward_fertilizer('two', NOW + REWARD_INTERVAL - 1))
        self.assertFalse(garden.reward_fertilizer('one', NOW + REWARD_INTERVAL))
        self.assertTrue(garden.reward_fertilizer('two', NOW + REWARD_INTERVAL))
        garden.advance(NOW + 72 * HOUR)
        self.assertEqual(garden.fertilizer, 2)
        self.assertTrue(garden.can_reward_fertilizer)
        garden.fertilizer = FERTILIZER_CAP
        self.assertFalse(garden.reward_fertilizer('full', garden.last_update))
        self.assertEqual(garden.reward_wait, 0)

    def test_vacation_freezes_all_cooldowns_and_backward_clock_does_not_rewind(self):
        garden = growing('daisy')
        garden.care('mist', NOW)
        garden.reward_fertilizer('one', NOW)
        garden.set_vacation(True, NOW)
        garden.advance(NOW + 20 * HOUR)
        self.assertEqual((garden.growth, garden.pot['water_wait'], garden.pot['mist_wait'], garden.reward_wait),
                         (60, WATER_INTERVAL, MIST_INTERVAL, REWARD_INTERVAL))
        self.assertFalse(garden.use_fertilizer(NOW + 20 * HOUR))
        self.assertFalse(garden.reward_fertilizer('two', NOW + 20 * HOUR))
        garden.set_vacation(False, NOW + 20 * HOUR)
        garden.advance(NOW + 20 * HOUR + 300)
        before = garden.to_dict()
        garden.advance(NOW)
        self.assertEqual(garden.to_dict(), before)
        self.assertEqual(garden.reward_wait, REWARD_INTERVAL - 300)

    def test_planned_starflower_timing_matches_design(self):
        for fertilizers, bloom_seconds in ((0, 9240), (1, 8880), (4, 7200)):
            garden = growing()
            garden.care('mist', NOW)
            garden.fertilizer = fertilizers
            for _ in range(fertilizers):
                garden.use_fertilizer(NOW)
            for elapsed in range(60, bloom_seconds + 1, 60):
                garden.advance(NOW + elapsed)
                if elapsed % WATER_INTERVAL == 0:
                    garden.care('water', NOW + elapsed)
                if elapsed % MIST_INTERVAL == 0:
                    garden.care('mist', NOW + elapsed)
                self.assertEqual(garden.bloomed, elapsed == bloom_seconds)

    def test_v5_migration_preserves_active_rules_and_original_backup(self):
        old = v5_data(growing('tulip'))
        old['pots'][0]['care_elapsed'] = 40 * HOUR
        old['pots'][0]['growth'] = 35 * HOUR
        old['coins'] = 432
        source = deepcopy(old)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            raw = json.dumps(old)
            store.path.write_text(raw, encoding='utf-8')
            garden = store.load(NOW)
            self.assertEqual((garden.schema, garden.coins, garden.water_status), (6, 432, 'slow'))
            self.assertFalse(garden.can_use_fertilizer)
            store.save(garden)
            self.assertEqual(store.migration_backup.name, 'garden.json.v5-migration.bak')
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            garden.care('water', NOW)
            self.assertTrue(garden.harvest(NOW + 13 * HOUR))
            garden.seeds['tulip'] = 1
            garden.plant(NOW + 13 * HOUR, 'tulip')
            self.assertEqual(garden.pot['ruleset_id'], TYCOON_RULE)
        migrate(old)
        self.assertEqual(old, source)

    def test_new_save_fields_reject_malformed_values(self):
        base = growing().to_dict()
        for key, value in (('fertilizer', True), ('fertilizer', 11), ('reward_wait', float('nan')),
                           ('reward_wait', -1), ('last_reward_id', 12)):
            data = deepcopy(base)
            data[key] = value
            with self.assertRaises(ValueError):
                Garden.from_dict(data)
        for key, value in (('water_wait', True), ('mist_wait', -1), ('fertilizer_used', 5),
                           ('mist_count', True), ('water_count', 0)):
            data = deepcopy(base)
            data['pots'][0][key] = value
            with self.assertRaises(ValueError):
                Garden.from_dict(data)
        empty = Garden(NOW).to_dict()
        empty['pots'][0]['water_wait'] = False
        with self.assertRaises(ValueError):
            Garden.from_dict(empty)


class TycoonUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.time_patch = patch('morning_bloom.app.time.time', return_value=NOW)
        self.wall_clock = self.time_patch.start()
        self.store = Store(Path(self.temp.name) / 'garden.json')
        self.garden = growing('daisy')
        self.garden.fertilizer = 2
        self.window = Window(self.store, self.garden)
        self.window.show()
        self.app.processEvents()
        self.window.persist()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.time_patch.stop()
        self.temp.cleanup()

    def play_success(self, game):
        with patch('morning_bloom.fertilizer_game.random.uniform', return_value=.35), \
                patch('morning_bloom.fertilizer_game.time.monotonic', return_value=100) as clock:
            game.start()
            for now in (100.5, 101.1, 101.7):
                clock.return_value = now
                game.stop_round()

    def test_fertilizer_and_care_save_failure_restore_state_and_effect(self):
        self.garden.advance(NOW + 1800)
        self.wall_clock.return_value = NOW + 1800
        self.window.refresh()
        before = self.garden.to_dict()
        self.window.flower.drops = 0
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.assertFalse(self.window.use_fertilizer())
            self.assertEqual(self.garden.to_dict(), before)
            self.assertFalse(self.window.care('water'))
            self.assertEqual(self.garden.to_dict(), before)
        self.assertEqual(self.window.flower.drops, 0)

    def test_real_game_awards_once_and_practice_cannot_become_rewarded(self):
        self.window.open_fertilizer_game()
        game = self.window._fertilizer_game
        self.play_success(game)
        self.assertEqual((self.garden.fertilizer, self.garden.reward_wait), (3, 1800))
        game.stop_round()
        self.assertEqual(self.garden.fertilizer, 3)
        game.reject()
        self.window.open_fertilizer_game()
        practice = self.window._fertilizer_game
        self.assertFalse(practice.rewarded)
        self.wall_clock.return_value = NOW + 1800
        self.window.refresh()
        self.play_success(practice)
        self.assertEqual(self.garden.fertilizer, 3)
        self.assertEqual(self.garden.reward_wait, 0)

    def test_reward_save_failure_rolls_back_and_allows_new_attempt(self):
        self.window.open_fertilizer_game()
        game = self.window._fertilizer_game
        with patch.object(self.store, 'save', side_effect=SaveError('disk full')):
            self.play_success(game)
        self.assertEqual((self.garden.fertilizer, self.garden.reward_wait, self.garden.last_reward_id),
                         (2, 0, None))
        self.assertTrue(self.garden.can_reward_fertilizer)
        self.assertIn('받지 못했어요', game.result.text())

    def test_double_click_keyboard_and_timeout_do_not_duplicate_rounds(self):
        self.window.open_fertilizer_game()
        game = self.window._fertilizer_game
        game.activateWindow()
        game.setFocus()
        self.app.processEvents()
        with patch('morning_bloom.fertilizer_game.random.uniform', return_value=.35), \
                patch('morning_bloom.fertilizer_game.time.monotonic', return_value=100) as clock:
            game.start()
            clock.return_value = 100.5
            QTest.keyClick(game, Qt.Key_Space)
            self.assertEqual(game.round, 2)
            clock.return_value = 100.6
            game.stop_round()
            self.assertEqual(game.round, 2)
            clock.return_value = 113
            game.tick()
            self.assertTrue(game.finished_game)
            self.assertFalse(game.running)
            self.assertEqual(self.garden.fertilizer, 2)

    def test_focus_loss_mode_switch_and_full_inventory_cancel_or_practice(self):
        self.window.open_fertilizer_game()
        game = self.window._fertilizer_game
        game.start()
        game.eventFilter(self.app, QEvent(QEvent.ApplicationDeactivate))
        self.assertIsNone(self.window._fertilizer_game)
        self.assertEqual(self.garden.reward_wait, 0)
        self.window.open_fertilizer_game()
        self.assertTrue(self.window.set_developer_mode(True))
        self.assertIsNone(self.window._fertilizer_game)
        self.assertEqual(self.garden.fertilizer, 0)
        self.assertTrue(self.window.set_developer_mode(False))
        self.assertEqual(self.garden.fertilizer, 2)
        self.garden.fertilizer = 10
        self.window.open_fertilizer_game()
        self.assertFalse(self.window._fertilizer_game.rewarded)

    def test_four_pot_layout_and_summary_at_three_sizes(self):
        self.garden.coins = 1000
        while self.garden.buy_pot():
            pass
        self.window.refresh()
        self.assertIn('화분 1 / 4', self.window.pot_name.text())
        self.assertIn('분무 1', self.window.status.text())
        for side in (320, 384, 520):
            self.window.setFixedSize(side, side)
            self.app.processEvents()
            self.assertGreater(self.window.flower.height(), 0)
            for widget in (self.window.water_button, self.window.mist_button, self.window.fertilizer_button,
                           self.window.make_fertilizer_button, self.window.harvest_button):
                self.assertTrue(widget.isVisible())
                self.assertTrue(self.window.rect().contains(widget.mapTo(self.window, widget.rect().bottomRight())))
        self.window.next_pot.click()
        self.assertFalse(self.window.fertilizer_button.isEnabled())
        self.window.pot_slides.finish_transition()
        for side in (320, 384, 520):
            self.window.setFixedSize(side, side)
            self.app.processEvents()
            self.assertGreater(self.window.flower.height(), 0)
            self.assertTrue(self.window.rect().contains(
                self.window.plant_button.mapTo(self.window, self.window.plant_button.rect().bottomRight())))
        self.assertFalse(self.window.next_pot.icon().isNull())


if __name__ == '__main__':
    unittest.main()
