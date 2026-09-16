import unittest

from morning_bloom.model import DAY, HOUR, Garden


def ready_garden(species, now=0):
    seeds = {'daisy': 0, 'starflower': 0, 'tulip': 0}
    seeds[species] = 1
    garden = Garden(now, tutorial_used=True, tutorial_reward_claimed=True, seeds=seeds)
    assert garden.plant(now, species)
    assert garden.care('water', now)
    return garden


class GrowthRules(unittest.TestCase):
    def test_first_flower_waits_for_water_and_rewards_once(self):
        garden = Garden(100)
        self.assertFalse(garden.plant(100, 'starflower'))
        self.assertTrue(garden.plant(100, 'daisy'))
        garden.advance(1000)
        self.assertEqual(garden.growth, 0)
        self.assertIsNone(garden.remaining_seconds())
        self.assertTrue(garden.care('water', 1000))
        self.assertFalse(garden.harvest(1059))
        self.assertTrue(garden.harvest(1060))
        self.assertEqual(garden.seed_count('daisy'), 1)
        self.assertFalse(garden.harvest(1060))
        garden.plant(1060, 'daisy')
        self.assertEqual(garden.duration, DAY)

    def test_starflower_is_three_hours_and_mist_adds_one_gold(self):
        garden = ready_garden('starflower')
        plant_id = garden.pot['plant_id']
        self.assertEqual(garden.duration, 3 * HOUR)
        self.assertTrue(garden.care('mist', HOUR))
        self.assertFalse(garden.care('mist', HOUR))
        self.assertTrue(garden.harvest(3 * HOUR))
        flower = garden.collection[0]
        self.assertEqual(flower['id'], plant_id)
        self.assertEqual((flower['base_sale_g'], flower['bonus_g']), (12, 1))
        self.assertTrue(garden.sell(plant_id))
        self.assertEqual(garden.coins, 133)

    def test_daisy_needs_no_second_watering(self):
        garden = ready_garden('daisy')
        self.assertEqual(garden.water_status, 'done')
        self.assertFalse(garden.care('water', 23 * HOUR))
        garden.advance(DAY)
        self.assertTrue(garden.bloomed)

    def test_tulip_watering_boundaries(self):
        garden = ready_garden('tulip')
        garden.advance(22 * HOUR - 1)
        self.assertEqual(garden.water_status, 'waiting')
        self.assertFalse(garden.care('water', 22 * HOUR - 1))
        garden.advance(22 * HOUR)
        self.assertEqual(garden.water_status, 'early')
        garden.advance(24 * HOUR)
        self.assertEqual(garden.water_status, 'due')
        garden.advance(30 * HOUR)
        self.assertEqual(garden.water_status, 'slow')

    def test_tulip_without_second_water_blooms_at_66_hours(self):
        garden = ready_garden('tulip')
        garden.advance(48 * HOUR)
        self.assertEqual(garden.growth, 39 * HOUR)
        self.assertFalse(garden.bloomed)
        garden.advance(66 * HOUR - 1)
        self.assertFalse(garden.bloomed)
        garden.advance(66 * HOUR)
        self.assertTrue(garden.bloomed)

    def test_tulip_water_at_40_hours_blooms_at_53(self):
        garden = ready_garden('tulip')
        garden.advance(40 * HOUR)
        self.assertEqual(garden.growth, 35 * HOUR)
        self.assertEqual(garden.remaining_seconds(), 26 * HOUR)
        self.assertEqual(garden.remaining_seconds(water_now=True), 13 * HOUR)
        self.assertTrue(garden.care('water', 40 * HOUR))
        garden.advance(53 * HOUR - 1)
        self.assertFalse(garden.bloomed)
        garden.advance(53 * HOUR)
        self.assertTrue(garden.bloomed)

    def test_tulip_early_water_keeps_48_hour_bloom(self):
        garden = ready_garden('tulip')
        self.assertTrue(garden.care('water', 22 * HOUR))
        garden.advance(48 * HOUR)
        self.assertTrue(garden.bloomed)

    def test_offline_growth_is_capped_and_time_never_rewinds(self):
        garden = ready_garden('daisy', 100)
        garden.pot['duration'] = 100 * DAY
        garden.advance(100 + 10 * DAY)
        self.assertEqual(garden.growth, 3 * DAY)
        state = garden.to_dict()
        garden.advance(1)
        self.assertEqual(garden.to_dict(), state)

    def test_vacation_freezes_growth_and_care_age(self):
        garden = ready_garden('tulip', 100)
        garden.set_vacation(True, 100 + HOUR)
        garden.advance(100 + 20 * DAY)
        garden.set_vacation(False, 100 + 20 * DAY)
        self.assertEqual((garden.growth, garden.pot['care_elapsed']), (HOUR, HOUR))


if __name__ == '__main__':
    unittest.main()
