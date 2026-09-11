import json
import tempfile
import unittest
from pathlib import Path
from morning_bloom.model import Garden, SingleGarden, DAY
from morning_bloom.storage import Store

class Expansion(unittest.TestCase):
    def test_purchase_limits(self):
        g=Garden(100)
        self.assertFalse(g.buy_pot())
        g.coins=170
        self.assertTrue(g.buy_pot())
        self.assertFalse(g.buy_pot())
        self.assertTrue(g.buy_seed())
        self.assertFalse(g.buy_seed())
        self.assertEqual((g.coins,g.seed_count('daisy'),len(g.pots)),(0,2,2))

    def test_two_pots_independent_and_one_tutorial(self):
        g=Garden(100,coins=200,seeds={'daisy':2,'tulip':1})
        g.buy_pot();g.plant(100);g.select(1);g.plant(110,'tulip')
        g.advance(160)
        self.assertEqual(g.growth,50)
        self.assertEqual(g.duration,2*DAY)
        self.assertFalse(g.harvest(160))
        g.select(0)
        self.assertTrue(g.bloomed)
        self.assertTrue(g.harvest(160))
        self.assertFalse(g.harvest(160))
        self.assertEqual(g.seed_count('daisy'),2)
        g.select(1)
        self.assertEqual(g.species,'tulip')
        self.assertFalse(g.select(2))

    def test_care_and_vacation_across_pots(self):
        g=Garden(100,coins=200,tutorial_used=True,seeds={'daisy':2,'tulip':0})
        g.buy_pot();g.plant(100);g.water_due=100;g.duration=10*DAY
        g.select(1);g.plant(100);g.water_due=100;g.duration=10*DAY
        g.care('water',100)
        self.assertEqual(g.water_due,100+2*DAY)
        g.select(0);self.assertEqual(g.water_due,100)
        g.set_vacation(True,100);g.advance(100+5*DAY)
        self.assertEqual(g.growth,0)
        g.select(1);self.assertEqual(g.growth,0)

    def test_sale_by_id_preserves_other_species(self):
        g=Garden(100)
        g.collection=[dict(id='a',species='daisy',harvested_at=100),dict(id='b',species='tulip',harvested_at=100)]
        self.assertTrue(g.sell('a'));self.assertFalse(g.sell('a'))
        self.assertEqual(g.coins,170)
        self.assertEqual(g.collection[0]['species'],'tulip')

    def test_v2_migrates_and_two_pots_roundtrip(self):
        old=SingleGarden(100,tutorial_used=True,seeds={'daisy':1,'tulip':1})
        old.plant(100,'tulip');old.advance(120)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'garden.json')
            raw=json.dumps(old.to_dict());store.path.write_text(raw)
            g=store.load(120)
            self.assertEqual((g.schema,g.species,g.growth),(3,'tulip',20))
            g.coins=200;g.buy_pot();g.select(1);g.plant(120)
            store.save(g)
            self.assertEqual(store.backup.read_text(),raw)
            self.assertEqual(store.load(130).to_dict(),g.to_dict())

    def test_invalid_pot_count_and_selection(self):
        for key,value in [('selected',2),('pots',[]),('pots',[{}, {}, {}])]:
            data=Garden(100).to_dict();data[key]=value
            with self.assertRaises(ValueError):Garden.from_dict(data)
