"""Board probabilities, week boundaries and restart-safe reward delivery."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from morning_bloom import board_model as board
from morning_bloom.content import ITEMS, BY_DESIGN, POOLS, NEW_PLANTS
from morning_bloom.model import Garden
from morning_bloom.storage import SaveError, Store, migrate
from morning_bloom.save_v13_model import Garden as OldGarden

NOW=1_700_000_000

def draws(*values):
    values=iter(values)
    def draw(n):
        value=next(values)
        assert 0<=value<n
        return value
    return draw

class BoardRules(unittest.TestCase):
    def test_catalog_and_category_scoped_identity(self):
        self.assertEqual(len(ITEMS),150)
        self.assertEqual(sum(x['board_eligible'] for x in ITEMS),140)
        self.assertTrue(all(POOLS.values()))
        self.assertNotIn('ancient',sum(POOLS.values(),()))
        self.assertNotIn('dandelion',sum(POOLS.values(),()))
        self.assertEqual(len(NEW_PLANTS),8)

    def test_all_120_moves_only_landings_trigger_two_gates(self):
        hits=0
        for start in range(20):
            for face in range(6):
                g=Garden(NOW);g.progression['tickets']=1
                g.progression['board']['position']=start
                self.assertTrue(board.prepare(g,draw=draws(face,0,0)))
                plan=board.commit(g)
                self.assertEqual(plan['target'],(start+face+1)%20)
                special=plan['target'] in board.GATES
                self.assertEqual(g.progression['board']['special'] is not None,special)
                self.assertEqual(g.progression['board']['completed'],int(not special))
                self.assertEqual(g.progression['tickets'],0)
                Garden.from_dict(g.to_dict())
                hits+=special
        self.assertEqual(hits,12)

    def test_normal_grade_tickets_are_exactly_five_three_one(self):
        grades=[]
        for ticket in range(9):
            g=Garden(NOW);g.progression['tickets']=1
            board.prepare(g,draw=draws(0,ticket,0));plan=board.commit(g)
            grades.append(plan['reward']['grade'])
            self.assertEqual(plan['reward']['category'],'garden')
        self.assertEqual(grades,['C']*5+['B']*3+['A'])

    def test_all_six_special_outcomes_are_free_and_restore_gate(self):
        for gate in board.GATES:
            for face,(grade,category) in enumerate(board.SPECIAL):
                g=Garden(NOW);g.progression['tickets']=1
                g.progression['board']['position']=gate-1
                board.prepare(g,draw=draws(0,face,0));board.commit(g)
                self.assertEqual(g.progression['petals'],0)
                self.assertFalse(board.prepare(g,'roll'))
                g=Garden.from_dict(g.to_dict())
                self.assertTrue(board.prepare(g,'special',draw=lambda n:self.fail('rerolled')))
                plan=board.commit(g)
                self.assertEqual((plan['reward']['grade'],plan['reward']['category']),(grade,category))
                self.assertEqual(g.progression['board']['position'],gate)
                self.assertEqual(g.progression['board']['completed'],1)
                self.assertEqual(g.progression['tickets'],0)
                Garden.from_dict(g.to_dict())

    def test_weekly_korea_midnight_carryover_no_backfill_or_rewind(self):
        stamp=lambda s:datetime.fromisoformat(s).timestamp()
        g=Garden(NOW)
        sunday=stamp('2026-10-18T23:59:59+09:00')
        monday=sunday+1
        self.assertTrue(g.claim_weekly(sunday));self.assertEqual(g.progression['tickets'],5)
        self.assertFalse(g.claim_weekly(sunday))
        self.assertTrue(g.claim_weekly(monday));self.assertEqual(g.progression['tickets'],10)
        self.assertFalse(g.claim_weekly(sunday))
        self.assertTrue(g.claim_weekly(monday+10*7*86400))
        self.assertEqual(g.progression['tickets'],15)
        Garden.from_dict(g.to_dict())

    def test_duplicate_petals_seed_copy_and_unowned_only_exchange(self):
        g=Garden(NOW)
        first=board.grant(g,dict(category='plant',grade='C',item_id='daisy'))
        self.assertTrue(first['duplicate']);self.assertEqual(first['petals'],2)
        self.assertEqual(g.seeds['daisy'],2)
        item=next(x for x in ITEMS if x['item_id']==NEW_PLANTS[0])
        key=item['item_id'];g.progression['petals']=board.EXCHANGE[item['grade']]
        self.assertTrue(g.exchange_item('plant',key));self.assertEqual(g.progression['petals'],0)
        self.assertEqual(g.seeds[key],1)
        self.assertFalse(g.exchange_item('plant',key))
        self.assertFalse(g.exchange_item('plant','ancient'))
        self.assertFalse(g.exchange_item('plant','dandelion'))
        Garden.from_dict(g.to_dict())

    def test_new_species_requires_unlock_then_repurchase_is_available(self):
        g=Garden(NOW,coins=1000,tutorial_used=True,tutorial_reward_claimed=True)
        key=NEW_PLANTS[0]
        self.assertFalse(g.buy_seed(key));self.assertFalse(g.plant(NOW,key))
        board.grant(g,dict(category='plant',grade='S',item_id=key))
        self.assertTrue(g.plant(NOW,key));self.assertTrue(g.care('water',NOW))
        self.assertTrue(g.harvest(NOW+g.duration));self.assertTrue(g.buy_seed(key))
        self.assertTrue(g.plant(g.last_update,key))
        Garden.from_dict(g.to_dict())

    def test_v13_active_crop_keeps_old_rules_and_metadata_without_retroactive_effect(self):
        old=OldGarden(NOW,tutorial_used=True,tutorial_reward_claimed=True)
        old.plant(NOW);old.care('water',NOW);old.care('mist',NOW)
        original=old.to_dict();upgraded=migrate(original)
        self.assertEqual({k:v for k,v in upgraded.items() if k!='progression'},{**original,'schema':14})
        self.assertEqual(upgraded['progression']['crops'],{})
        g=Garden.from_dict(upgraded);g.advance(NOW+3600)
        self.assertEqual(g.growth,3660)
        self.assertEqual(original['schema'],13)

    def test_bad_progression_is_rejected(self):
        for field,value in (('unlocked',[{}]),('first_harvest',[[]]),('slots',[]),('tickets',True),('week','2026-10-18')):
            data=Garden(NOW).to_dict();data['progression'][field]=value
            with self.assertRaises(ValueError,msg=field):Garden.from_dict(data)
        data=Garden(NOW).to_dict();data['progression']={}
        with self.assertRaises(ValueError):Garden.from_dict(data)

class DurableBoard(unittest.TestCase):
    def test_failure_before_plan_keeps_ticket_and_failure_after_plan_replays_once(self):
        for fail_at in (1,2):
            with tempfile.TemporaryDirectory() as tmp:
                class FailingStore(Store):
                    calls=0
                    def save(self,g):
                        self.calls+=1
                        if self.calls==fail_at:raise SaveError('disk full')
                        return super().save(g)
                g=Garden(NOW);g.progression['tickets']=1
                path=Path(tmp)/'garden.json';Store(path).save(g)
                store=FailingStore(path);before=deepcopy(g.to_dict())
                with self.assertRaises(SaveError):board.transact(g,store,draw=draws(0,0,0))
                if fail_at==1:
                    self.assertEqual(g.to_dict(),before)
                    self.assertEqual(Store(path).load(NOW).to_dict(),before)
                else:
                    prepared=deepcopy(g.progression['board']['prepared'])
                    self.assertIsNotNone(prepared)
                    reopened=Store(path).load(NOW)
                    self.assertEqual(reopened.progression['tickets'],0)
                    self.assertEqual(reopened.progression['board']['completed'],1)
                    self.assertEqual(reopened.progression['board']['last_result']['item_id'],prepared['reward']['item_id'])
                    self.assertFalse(board.transact(reopened,Store(path)))
                    self.assertEqual(Store(path).load(NOW).to_dict(),reopened.to_dict())

    def test_retry_in_same_process_reuses_fixed_special_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=Garden(NOW);g.progression['tickets']=1;g.progression['board']['position']=7
            store=Store(Path(tmp)/'garden.json')
            board.prepare(g,draw=draws(0,5,0));store.save(g)
            board.transact(g,store,draw=lambda n:self.fail('rerolled'))
            self.assertEqual(g.progression['board']['special']['die'],6)
            board.transact(g,store,'special',draw=lambda n:self.fail('rerolled'))
            self.assertEqual(g.progression['board']['last_result']['grade'],'S')
            self.assertEqual(g.progression['board']['last_result']['category'],'pot')
            self.assertEqual(g.progression['board']['paid'],1)
            self.assertEqual(g.progression['board']['completed'],1)
