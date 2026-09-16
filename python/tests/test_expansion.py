import json
import tempfile
import unittest
from pathlib import Path

from morning_bloom.model import DAY, HOUR, Garden, SingleGarden
from morning_bloom.storage import SaveError, Store


class EconomyAndPots(unittest.TestCase):
    def test_purchase_limits_and_prices(self):
        garden = Garden(100)
        self.assertFalse(garden.buy_pot())
        garden.coins = 200
        self.assertTrue(garden.buy_pot())
        self.assertFalse(garden.buy_pot())
        self.assertTrue(garden.buy_seed('starflower'))
        self.assertTrue(garden.buy_seed('tulip'))
        self.assertEqual((garden.coins, garden.seed_count('starflower')), (7, 1))
        self.assertFalse(garden.buy_seed('starflower'))

    def test_two_pots_grow_independently(self):
        seeds = {'daisy': 1, 'starflower': 1, 'tulip': 0}
        garden = Garden(100, tutorial_used=True, tutorial_reward_claimed=True, coins=200, seeds=seeds)
        garden.buy_pot()
        garden.plant(100, 'daisy')
        garden.care('water', 100)
        garden.select(1)
        garden.plant(100, 'starflower')
        garden.advance(100 + 4 * HOUR)
        self.assertEqual(garden.growth, 0)
        garden.care('water', 100 + 4 * HOUR)
        garden.select(0)
        self.assertEqual(garden.growth, 4 * HOUR)
        garden.advance(100 + 7 * HOUR)
        garden.select(1)
        self.assertTrue(garden.bloomed)
        garden.select(0)
        self.assertFalse(garden.bloomed)

    def test_sale_uses_harvest_snapshot(self):
        garden = Garden(100)
        garden.collection = [{
            'id': 'old-price', 'species': 'daisy', 'harvested_at': 90,
            'base_sale_g': 41, 'misted': True, 'bonus_g': 4,
        }]
        self.assertTrue(garden.sell('old-price'))
        self.assertEqual(garden.coins, 165)
        self.assertFalse(garden.sell('old-price'))

    def test_vacation_allows_inventory_but_blocks_growing_actions(self):
        garden = Garden(0, tutorial_used=True, tutorial_reward_claimed=True,
                        seeds={'daisy': 1, 'starflower': 0, 'tulip': 0})
        garden.plant(0, 'daisy')
        garden.care('water', 0)
        garden.advance(DAY)
        garden.set_vacation(True, DAY)
        self.assertTrue(garden.harvest(DAY))
        self.assertTrue(garden.sell())
        self.assertTrue(garden.buy_seed('starflower'))
        self.assertFalse(garden.plant(DAY, 'daisy'))


class SaveMigration(unittest.TestCase):
    def test_v2_active_plant_migrates_to_v5_with_exemption(self):
        legacy = SingleGarden(100, tutorial_used=True, seeds={'daisy': 0, 'tulip': 1})
        legacy.plant(100, 'tulip')
        legacy.advance(100 + 40 * HOUR)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            raw = json.dumps(legacy.to_dict(), ensure_ascii=False)
            store.path.write_text(raw, encoding='utf-8')
            garden = store.load(100 + 40 * HOUR)
            self.assertEqual(garden.schema, 5)
            self.assertTrue(garden.pot['initial_watered'])
            self.assertTrue(garden.pot['legacy_care_exempt'])
            self.assertEqual(garden.seed_count('starflower'), 0)
            garden.advance(100 + 48 * HOUR)
            self.assertTrue(garden.bloomed)
            store.save(garden)
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)

    def test_v1_collection_gets_fixed_old_price(self):
        legacy = {
            'last_update': 100, 'schema': 1, 'planted': False,
            'growth': 0, 'duration': DAY, 'water_due': 1000, 'mist_due': 1000,
            'tutorial_used': True, 'coins': 145, 'seeds': 2,
            'collection': [{'id': 'legacy-flower', 'species': 'daisy', 'harvested_at': 90}],
            'vacation': False,
            'settings': {'opacity': .8, 'topmost': True, 'x': 10, 'y': 20},
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(json.dumps(legacy), encoding='utf-8')
            garden = store.load(100)
            self.assertEqual(garden.seeds, {'daisy': 2, 'starflower': 0, 'tulip': 0})
            self.assertEqual(garden.collection[0]['base_sale_g'], 50)
            self.assertEqual(garden.collection[0]['bonus_g'], 0)

    def test_roundtrip_backup_recovery_and_future_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            garden = Garden(100)
            store.save(garden)
            garden.coins = 121
            store.save(garden)
            store.path.write_text('broken', encoding='utf-8')
            self.assertEqual(Store(store.path).load(100).coins, 120)
            store.path.write_text('{"schema": 6}', encoding='utf-8')
            blocked = Store(store.path)
            with self.assertRaises(SaveError):
                blocked.load(100)
            with self.assertRaises(SaveError):
                blocked.save(garden)

    def test_duplicate_flower_ids_are_rejected(self):
        data = Garden(100).to_dict()
        item = {
            'id': 'same', 'species': 'daisy', 'harvested_at': 90,
            'base_sale_g': 50, 'misted': False, 'bonus_g': 0,
        }
        data['collection'] = [item, dict(item)]
        with self.assertRaises(ValueError):
            Garden.from_dict(data)

    def test_nan_and_invalid_bonus_are_rejected(self):
        data = Garden(100).to_dict()
        data['last_update'] = float('nan')
        with self.assertRaises(ValueError):
            Garden.from_dict(data)
        data = Garden(100).to_dict()
        data['collection'] = [{
            'id': 'flower', 'species': 'starflower', 'harvested_at': 90,
            'base_sale_g': 12, 'misted': True, 'bonus_g': 2,
        }]
        with self.assertRaises(ValueError):
            Garden.from_dict(data)


if __name__ == '__main__':
    unittest.main()
