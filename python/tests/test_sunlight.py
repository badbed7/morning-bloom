import json
import tempfile
import unittest
from pathlib import Path

from morning_bloom.cosmetics import POT_SKINS
from morning_bloom.model import Garden, SUN_INTERVAL, SUN_PENDING_CAP, TYCOON_POT_DEFAULTS, V8_FIELDS
from morning_bloom.storage import SaveError, Store


def flower(index=0, species='daisy'):
    return {
        'id': f'flower-{index}', 'species': species, 'harvested_at': 10,
        'base_sale_g': 50, 'misted': False, 'bonus_g': 0,
    }


def v4_data(garden):
    data = garden.to_dict()
    for key in V8_FIELDS:
        data.pop(key)
    for key in (
        'sunlight', 'sun_tokens', 'sun_elapsed', 'sun_cursor',
        'sun_intro_claimed', 'owned_themes', 'equipped_theme',
        'fertilizer', 'reward_wait', 'last_reward_id',
        'owned_skins', 'equipped_skin',
    ):
        data.pop(key)
    for pot in data['pots']:
        for key in TYCOON_POT_DEFAULTS:
            pot.pop(key)
    data['schema'] = 4
    return data


class SunlightProduction(unittest.TestCase):
    def test_first_harvest_creates_one_intro_sun_only_once(self):
        garden = Garden(0)
        garden.plant(0)
        garden.care('water', 0)
        garden.harvest(60)
        self.assertEqual(len(garden.sun_tokens), 1)
        self.assertTrue(garden.sun_intro_claimed)
        token = garden.sun_tokens[0]
        self.assertEqual(token['source_flower_id'], garden.collection[0]['id'])
        self.assertTrue(garden.collect_sun(token['id'], 60))
        self.assertEqual(garden.sunlight, 1)
        self.assertFalse(garden.collect_sun(token['id'], 60))
        garden.collection.append(flower(2))
        self.assertEqual(len(garden.sun_tokens), 0)

    def test_twenty_minute_boundary_produces_one_per_flower(self):
        garden = Garden(100, collection=[flower(0), flower(1)])
        garden.sun_intro_claimed = True
        garden.advance(100 + SUN_INTERVAL - 1)
        self.assertEqual(garden.sun_tokens, [])
        self.assertEqual(garden.seconds_to_sun, 1)
        garden.advance(100 + SUN_INTERVAL)
        self.assertEqual(len(garden.sun_tokens), 2)
        self.assertEqual({token['source_flower_id'] for token in garden.sun_tokens},
                         {'flower-0', 'flower-1'})
        self.assertEqual(garden.seconds_to_sun, SUN_INTERVAL)

    def test_pending_cap_discards_backlog_and_resumes_next_round(self):
        garden = Garden(0, collection=[flower(0)])
        garden.sun_intro_claimed = True
        garden.advance(50 * SUN_INTERVAL)
        self.assertEqual(len(garden.sun_tokens), SUN_PENDING_CAP)
        ids = [token['id'] for token in garden.sun_tokens]
        for token_id in ids:
            self.assertTrue(garden.collect_sun(token_id))
        self.assertEqual(garden.sunlight, SUN_PENDING_CAP)
        garden.advance(50 * SUN_INTERVAL + SUN_INTERVAL - 1)
        self.assertEqual(garden.sun_tokens, [])
        garden.advance(51 * SUN_INTERVAL)
        self.assertEqual(len(garden.sun_tokens), 1)

    def test_vacation_freezes_production_without_catchup(self):
        garden = Garden(0, collection=[flower()])
        garden.sun_intro_claimed = True
        garden.advance(SUN_INTERVAL // 2)
        garden.set_vacation(True, SUN_INTERVAL // 2)
        garden.advance(20 * SUN_INTERVAL)
        self.assertEqual(garden.sun_tokens, [])
        self.assertEqual(garden.sun_elapsed, SUN_INTERVAL // 2)
        garden.set_vacation(False, 20 * SUN_INTERVAL)
        garden.advance(20 * SUN_INTERVAL + SUN_INTERVAL // 2)
        self.assertEqual(len(garden.sun_tokens), 1)

    def test_selling_settles_time_and_existing_sun_survives(self):
        garden = Garden(0, collection=[flower(0), flower(1)])
        garden.sun_intro_claimed = True
        self.assertTrue(garden.sell('flower-0', SUN_INTERVAL))
        self.assertEqual(len(garden.sun_tokens), 2)
        self.assertTrue(garden.sell('flower-1', SUN_INTERVAL))
        self.assertEqual(garden.collection, [])
        self.assertEqual(garden.sun_elapsed, 0)
        self.assertEqual(len(garden.sun_tokens), 2)
        garden.advance(10 * SUN_INTERVAL)
        self.assertEqual(len(garden.sun_tokens), 2)

    def test_many_flowers_rotate_sources_when_cap_limits_a_round(self):
        flowers = [flower(index) for index in range(12)]
        garden = Garden(0, collection=flowers, sun_intro_claimed=True)
        garden.advance(SUN_INTERVAL)
        self.assertEqual([token['source_flower_id'] for token in garden.sun_tokens],
                         [f'flower-{index}' for index in range(9)])
        for token in list(garden.sun_tokens):
            garden.collect_sun(token['id'])
        garden.advance(2 * SUN_INTERVAL)
        self.assertEqual([token['source_flower_id'] for token in garden.sun_tokens[:3]],
                         ['flower-9', 'flower-10', 'flower-11'])


class CosmeticsAndMigration(unittest.TestCase):
    def test_pot_skins_charge_sunlight_once_and_only_change_appearance(self):
        garden = Garden(100, coins=777, sunlight=11, collection=[flower()])
        self.assertFalse(garden.buy_skin('ivory'))
        self.assertFalse(garden.equip_skin('ivory'))
        garden.sunlight = 60
        before = garden.to_dict()
        for key in ('ivory', 'sage', 'rose'):
            self.assertTrue(garden.buy_skin(key))
            self.assertFalse(garden.buy_skin(key))
            self.assertTrue(garden.equip_skin(key))
        self.assertEqual(garden.sunlight, 60 - sum(POT_SKINS[key].price for key in ('ivory', 'sage', 'rose')))
        self.assertEqual(Garden.from_dict(garden.to_dict()).equipped_skin, 'rose')
        self.assertTrue(garden.equip_skin('terracotta'))
        after = garden.to_dict()
        for key in before.keys() - {'sunlight', 'owned_skins', 'equipped_skin'}:
            self.assertEqual(after[key], before[key], key)
        for invalid in ('missing', [], {}, None, True):
            self.assertFalse(garden.buy_skin(invalid))
            self.assertFalse(garden.equip_skin(invalid))

    def test_invalid_skin_ownership_and_unowned_equipment_are_rejected(self):
        for key, value in (
            ('owned_skins', []), ('owned_skins', ['terracotta', 'terracotta']),
            ('owned_skins', ['ivory']), ('owned_skins', ['terracotta', {}]),
            ('owned_skins', ['terracotta', 'missing']), ('equipped_skin', 'ivory'),
            ('equipped_skin', []),
        ):
            data = Garden(100).to_dict()
            data[key] = value
            with self.assertRaises(ValueError):
                Garden.from_dict(data)

    def test_v6_migration_preserves_inventory_and_creates_original_backup(self):
        data = Garden(100, coins=432, sunlight=30, fertilizer=2, collection=[flower()],
                      owned_themes=['grass', 'sky'], equipped_theme='sky').to_dict()
        additions = {key: data.pop(key) for key in V8_FIELDS}
        data.pop('owned_skins')
        data.pop('equipped_skin')
        data['schema'] = 6
        raw = json.dumps(data, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            garden = store.load(100)
            self.assertEqual(garden.to_dict(), {**data, **additions, 'schema': Garden.CURRENT_SCHEMA,
                                              'owned_skins': ['terracotta'], 'equipped_skin': 'terracotta'})
            store.save(garden)
            self.assertEqual(store.migration_backup.name, 'garden.json.v6-migration.bak')
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)
            self.assertTrue(garden.buy_skin('sage'))
            self.assertTrue(garden.equip_skin('sage'))
            store.save(garden)
            self.assertEqual((store.load(100).equipped_skin, store.load(100).sunlight), ('sage', 12))
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)

    def test_theme_purchase_and_apply_use_only_sunlight(self):
        garden = Garden(0)
        garden.sunlight = 11
        self.assertFalse(garden.buy_theme('cream'))
        garden.sunlight = 12
        self.assertTrue(garden.buy_theme('cream'))
        self.assertEqual(garden.sunlight, 0)
        self.assertIn('cream', garden.owned_themes)
        self.assertFalse(garden.buy_theme('cream'))
        self.assertFalse(garden.equip_theme('sky'))
        self.assertTrue(garden.equip_theme('cream'))
        self.assertEqual(garden.equipped_theme, 'cream')
        self.assertEqual(garden.coins, 120)

    def test_invalid_sun_and_cosmetic_data_are_rejected(self):
        cases = []
        data = Garden(0).to_dict()
        data['sunlight'] = -1
        cases.append(data)
        data = Garden(0).to_dict()
        data['sun_elapsed'] = SUN_INTERVAL
        cases.append(data)
        data = Garden(0).to_dict()
        data['sun_tokens'] = [{
            'id': 'same', 'source_flower_id': 'old', 'created_at': 0,
        }] * 2
        cases.append(data)
        data = Garden(0).to_dict()
        data['owned_themes'] = ['grass', 'grass']
        cases.append(data)
        data = Garden(0).to_dict()
        data['equipped_theme'] = 'sky'
        cases.append(data)
        for invalid in cases:
            with self.subTest(keys=list(invalid)):
                with self.assertRaises(ValueError):
                    Garden.from_dict(invalid)

    def test_v4_migration_preserves_game_and_grants_existing_garden_intro(self):
        original = Garden(100, coins=321, collection=[flower()])
        raw = json.dumps(v4_data(original), ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            migrated = store.load(100)
            self.assertEqual(migrated.schema, Garden.CURRENT_SCHEMA)
            self.assertEqual((migrated.coins, migrated.collection), (321, [flower()]))
            self.assertEqual(migrated.sunlight, 0)
            self.assertEqual(len(migrated.sun_tokens), 1)
            self.assertEqual(migrated.owned_themes, ['grass'])
            self.assertEqual(migrated.equipped_theme, 'grass')
            store.save(migrated)
            self.assertEqual(store.migration_backup.read_text(encoding='utf-8'), raw)

    def test_v4_without_flowers_waits_for_first_harvest(self):
        data = v4_data(Garden(100))
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(json.dumps(data), encoding='utf-8')
            migrated = store.load(100)
            self.assertFalse(migrated.sun_intro_claimed)
            self.assertEqual(migrated.sun_tokens, [])

    def test_malformed_v4_is_not_overwritten(self):
        data = v4_data(Garden(100))
        data['collection'] = [{'broken': True}]
        raw = json.dumps(data)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            store.path.write_text(raw, encoding='utf-8')
            with self.assertRaises(SaveError):
                store.load(100)
            self.assertEqual(store.path.read_text(encoding='utf-8'), raw)


if __name__ == '__main__':
    unittest.main()
