import json
import tempfile
import unittest
from pathlib import Path
from morning_bloom.model import Garden, DAY
from morning_bloom.storage import Store, SaveError

class Rules(unittest.TestCase):
    def test_complete_loop_and_no_duplicate_rewards(self):
        g = Garden(100)
        self.assertTrue(g.plant(100))
        self.assertFalse(g.plant(100))
        self.assertFalse(g.harvest(159))
        self.assertTrue(g.harvest(160))
        self.assertFalse(g.harvest(160))
        self.assertEqual(g.seeds['daisy'], 1)
        self.assertTrue(g.sell())
        self.assertFalse(g.sell())
        self.assertEqual(g.coins, 170)
        g.plant(160)
        self.assertEqual(g.duration, DAY)

    def test_early_care_does_not_extend(self):
        g = Garden(100)
        g.plant(100)
        due = g.water_due
        g.care('water', 110)
        self.assertEqual(g.water_due, due)
        self.assertEqual(g.growth, 10)

    def test_offline_cap_and_rollback(self):
        g = Garden(100, tutorial_used=True)
        g.plant(100)
        g.advance(100 + 10 * DAY)
        self.assertTrue(g.bloomed)
        self.assertEqual(g.water_due, 100 + 9 * DAY)
        old = g.to_dict()
        g.advance(1)
        self.assertEqual(old, g.to_dict())

    def test_wilt_and_recovery(self):
        g = Garden(100, tutorial_used=True)
        g.plant(100)
        g.duration = 10 * DAY
        g.advance(100 + 3 * DAY)
        self.assertEqual(g.growth, 3 * DAY)
        g.advance(100 + 4 * DAY)
        self.assertEqual(g.growth, 3 * DAY)
        g.care('water', 100 + 4 * DAY)
        g.care('mist', 100 + 4 * DAY)
        g.advance(100 + 4 * DAY + 20)
        self.assertEqual(g.growth, 3 * DAY + 20)

    def test_vacation_freezes_clocks(self):
        g = Garden(100)
        g.plant(100)
        g.set_vacation(True, 110)
        g.set_vacation(False, 110 + 10 * DAY)
        self.assertEqual(g.growth, 10)
        self.assertEqual(g.water_due, 100 + 12 * DAY)

    def test_validation(self):
        for key, value in [('coins', True), ('duration', 0), ('growth', float('nan')), ('seeds', -1), ('schema', 4)]:
            data = Garden(100).to_dict()
            if key in ('duration', 'growth'): data['pots'][0][key] = value
            else: data[key] = value
            with self.assertRaises(ValueError): Garden.from_dict(data)

    def test_tulip_uses_catalog_growth_and_prices(self):
        g = Garden(100, tutorial_used=True, seeds={'daisy': 0, 'tulip': 1})
        self.assertTrue(g.plant(100, 'tulip'))
        self.assertEqual(g.duration, 2 * DAY)
        self.assertEqual(g.species, 'tulip')
        g.advance(100 + 2 * DAY)
        self.assertTrue(g.harvest(100 + 2 * DAY))
        self.assertEqual(g.collection[-1]['species'], 'tulip')
        self.assertTrue(g.sell())
        self.assertEqual(g.coins, 220)

    def test_seed_is_bought_explicitly_at_species_price(self):
        g = Garden(100, tutorial_used=True, seeds={'daisy': 0, 'tulip': 0})
        self.assertFalse(g.plant(100, 'tulip'))
        self.assertEqual(g.coins, 120)
        self.assertTrue(g.buy_seed('tulip'))
        self.assertTrue(g.plant(100, 'tulip'))
        self.assertEqual(g.coins, 85)
        self.assertFalse(g.plant(100, 'daisy'))

    def test_first_tutorial_plant_must_be_daisy(self):
        g = Garden(100, seeds={'daisy': 1, 'tulip': 1})
        self.assertFalse(g.plant(100, 'tulip'))
        self.assertTrue(g.plant(100, 'daisy'))

class Saving(unittest.TestCase):
    def test_roundtrip_backup_recovery_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            g = Garden(100)
            store.save(g)
            g.plant(100)
            store.save(g)
            self.assertTrue(store.load(100).planted)
            store.path.write_text('broken')
            restored = store.load(100)
            self.assertFalse(restored.planted)
            backup = store.backup.read_bytes()
            store.save(restored)
            self.assertEqual(store.backup.read_bytes(), backup)

    def test_future_primary_not_replaced_by_old_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            g = Garden(100)
            store.save(g)
            store.save(g)
            store.path.write_text('{"schema": 4}')
            with self.assertRaises(SaveError): store.load(100)
            with self.assertRaises(SaveError): store.save(g)
            self.assertEqual(json.loads(store.path.read_text())['schema'], 4)

    def test_schema_one_save_is_migrated_without_data_loss(self):
        legacy = {
            'last_update': 100,
            'schema': 1,
            'planted': True,
            'growth': 20,
            'duration': DAY,
            'water_due': 1000,
            'mist_due': 1000,
            'tutorial_used': True,
            'coins': 145,
            'seeds': 2,
            'collection': [
                {'id': 'legacy-flower', 'species': 'daisy', 'harvested_at': 90}
            ],
            'vacation': False,
            'settings': {'opacity': .8, 'topmost': True, 'x': 10, 'y': 20},
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(json.dumps(legacy), encoding='utf-8')
            migrated = store.load(100)
            self.assertEqual(migrated.schema, 3)
            self.assertEqual(migrated.species, 'daisy')
            self.assertEqual(migrated.seeds, {'daisy': 2, 'tulip': 0})
            self.assertEqual(migrated.coins, 145)
            self.assertEqual(migrated.collection[0]['id'], 'legacy-flower')
            store.save(migrated)
            self.assertEqual(json.loads(store.path.read_text())['schema'], 3)

    def test_both_corrupt_block_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text('bad')
            with self.assertRaises(SaveError): store.load(100)
            with self.assertRaises(SaveError): store.save(Garden(100))

if __name__ == '__main__': unittest.main()

