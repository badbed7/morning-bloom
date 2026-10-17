from copy import deepcopy
import unittest
from morning_bloom import effects as fx
from morning_bloom.content import BY_DESIGN, ITEMS, NEW_PLANTS
from morning_bloom.model import Garden, HOUR, DAY

NOW=1_700_000_000

def equipped(theme='G-C00',skin='P-C00',species='daisy'):
    g=Garden(NOW,tutorial_used=True,tutorial_reward_claimed=True,coins=10000)
    for category,code in (('garden',theme),('pot',skin)):
        item=BY_DESIGN[code];owned=g.owned_themes if category=='garden' else g.owned_skins
        if item['item_id'] not in owned:owned.append(item['item_id'])
        (g.equip_theme if category=='garden' else g.equip_skin)(item['item_id'])
    if species not in g.progression['unlocked']:g.progression['unlocked'].append(species)
    g.seeds[species]=1
    assert g.plant(NOW,species)
    assert g.care('water',NOW)
    return g

class EquipmentEffects(unittest.TestCase):
    def test_every_equipment_definition_runs_complete_lifecycle_and_serializes(self):
        self.assertEqual(len(fx.SUPPORTED),128)
        for item in ITEMS:
            if item['category']=='plant':continue
            with self.subTest(item=item['design_id']):
                code=item['design_id']
                g=equipped(theme=code if code.startswith('G') else 'G-C00',skin=code if code.startswith('P') else 'P-C00')
                g.care('mist',NOW)
                for step in range(1,7):
                    now=NOW+step*1800;g.care('water',now);g.care('mist',now)
                g.fertilizer=5;g.use_fertilizer(g.last_update)
                g=Garden.from_dict(g.to_dict())
                g.advance(NOW+3*DAY,context='offline')
                self.assertTrue(g.harvest(g.last_update))
                g.advance(g.last_update+3600)
                Garden.from_dict(g.to_dict())
                g.sell();Garden.from_dict(g.to_dict())

    def test_default_grass_and_terracotta_effects(self):
        g=equipped();self.assertEqual(g.pot['water_wait'],1710)
        self.assertEqual(g.pot['mist_wait'],0)
        g.advance(NOW+3600);self.assertAlmostEqual(g.growth,3672)
        g.advance(NOW+7200);self.assertAlmostEqual(g.growth,7272)

    def test_first_water_snapshots_effects_but_slot_appearance_changes_immediately(self):
        g=equipped('G-S03','P-S01','rose');before=deepcopy(fx.crop(g,g.pot)['ids'])
        g.equip_theme('grass');g.equip_skin('terracotta')
        self.assertEqual(fx.crop(g,g.pot)['ids'],before)
        self.assertEqual(g.skin_for(g.pot['plant_id']),'terracotta')
        g.buy_pot();g.select(1)
        self.assertEqual(g.skin_for(g.pots[0]['plant_id']),'terracotta')
        g.select(0);g.advance(NOW+3600)
        self.assertAlmostEqual(g.growth,4140)

    def test_growth_boundaries_are_invariant_to_refresh_frequency(self):
        for theme,skin in (('G-C02','P-C05'),('G-C25','P-B05'),('G-A08','P-A06')):
            a=equipped(theme,skin,'lavender');a.care('mist',NOW)
            b=Garden.from_dict(a.to_dict());end=4*DAY
            a.advance(NOW+end,context='offline')
            for delta in range(137,end,137):b.advance(NOW+delta,context='offline')
            b.advance(NOW+end,context='offline')
            self.assertAlmostEqual(a.growth,b.growth,places=5)
            self.assertEqual(a.bloomed,b.bloomed)

    def test_sale_cap_is_additive_with_first_mist(self):
        g=equipped('G-S03','P-A02','rose');g.care('mist',NOW)
        base=g.pot['base_sale_g'];mist=g.pot['mist_bonus_g']
        g.growth=g.duration;g.harvest(NOW)
        self.assertEqual(g.collection[0]['bonus_g'],mist+int(base*.25))
        Garden.from_dict(g.to_dict())

    def test_fertilizer_limit_counts_actual_seconds_and_extra_shares_caps(self):
        for skin,fraction in (('P-C10',.26),('P-C00',.25)):
            g=equipped('G-S02',skin,'cosmos')
            for _ in range(200):
                g.fertilizer=5
                if not g.use_fertilizer(NOW):break
            c=fx.crop(g,g.pot)
            self.assertAlmostEqual(c['fertilizer'],g.duration*fraction)
            self.assertLessEqual(c['direct'],g.duration*.1)
            Garden.from_dict(g.to_dict())

    def test_stone_handle_first_fertilizer_preserves_one_required_inventory(self):
        g=equipped(skin='P-S03');self.assertEqual(g.fertilizer,0)
        self.assertFalse(g.can_use_fertilizer)
        g.fertilizer=1
        self.assertTrue(g.can_use_fertilizer);self.assertTrue(g.use_fertilizer(NOW))
        self.assertEqual(g.fertilizer,1);self.assertEqual(g.growth,600)
        self.assertTrue(g.use_fertilizer(NOW));self.assertEqual(g.fertilizer,0)
        self.assertFalse(g.can_use_fertilizer)

    def test_greenhouse_long_bonus_adds_to_base_and_caps_at_twenty_percent(self):
        g=equipped('G-S07','P-S01','tulip')
        self.assertAlmostEqual(fx.growth_rate(g,g.pot,'online'),1.2)
        g=equipped('G-S07',species='cosmos')
        self.assertAlmostEqual(fx.growth_rate(g,g.pot,'online'),1.2)

    def test_stage_reset_and_minigame_perks(self):
        g=equipped(skin='P-A07');g.advance(NOW+g.duration*.1)
        self.assertEqual(g.pot['water_wait'],0);self.assertEqual(g.pot['mist_wait'],0)
        self.assertEqual(fx.minigame_parameters(equipped(skin='P-C06'))['mist_clicks'],2)
        self.assertEqual(fx.minigame_parameters(equipped(skin='P-C12'))['mist_interval'],20)
        self.assertEqual(fx.minigame_parameters(equipped(skin='P-C16'))['fertilizer_width'],1.05)

    def test_first_spray_perks_keep_first_spray_immediate(self):
        for theme,reduction,species in (('G-C08',.05,'daisy'),('G-B24',.1,'rose')):
            g=equipped(theme=theme,species=species)
            self.assertTrue(g.can_care('mist'));g.care('mist',NOW)
            self.assertEqual(g.pot['mist_wait'],900*(1-reduction))

    def test_new_long_plants_keep_full_offline_growth(self):
        for species in NEW_PLANTS:
            g=equipped(species=species);duration=g.duration
            g.advance(NOW+30*DAY,context='offline')
            self.assertTrue(g.bloomed,species)
            self.assertEqual(g.growth,duration)

    def test_offline_sale_qualification_survives_reload(self):
        g=equipped('G-S01');g.advance(NOW+DAY,context='offline')
        self.assertTrue(fx.crop(g,g.pot)['offline_bloom'])
        g=Garden.from_dict(g.to_dict());g.harvest(g.last_update)
        self.assertEqual(g.collection[0]['bonus_g'],4)

    def test_sun_capacity_period_and_fractional_gold(self):
        g=equipped('G-S07');self.assertEqual(fx.sun_cap(g),14)
        fx.money(g,3500);fx.money(g,3500);before=g.coins
        fx.money(g,3500);self.assertEqual(g.coins,before+1);self.assertEqual(g.progression['fraction'],500)
        g.growth=g.duration;g.harvest(NOW);g.advance(NOW+DAY)
        self.assertEqual(len(g.sun_tokens),14)
        Garden.from_dict(g.to_dict())
