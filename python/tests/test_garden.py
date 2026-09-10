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
        self.assertEqual(g.seeds, 1)
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
        for key, value in [('coins', True), ('duration', 0), ('growth', float('nan')), ('seeds', -1), ('schema', 2)]:
            data = Garden(100).to_dict()
            data[key] = value
            with self.assertRaises(ValueError): Garden.from_dict(data)

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
            store.path.write_text('{"schema": 2}')
            with self.assertRaises(SaveError): store.load(100)
            with self.assertRaises(SaveError): store.save(g)
            self.assertEqual(json.loads(store.path.read_text())['schema'], 2)

    def test_both_corrupt_block_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text('bad')
            with self.assertRaises(SaveError): store.load(100)
            with self.assertRaises(SaveError): store.save(Garden(100))

if __name__ == '__main__': unittest.main()
