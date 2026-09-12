"""UI-independent real-time garden. Timestamps are UTC Unix seconds."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import ClassVar
from uuid import uuid4
import math

from .plant_catalog import DAY, HOUR, PLANTS, plant_definition

OFFLINE_CAP = 3 * DAY
MID_WATER_EARLY = 22 * HOUR
MID_WATER_DUE = 24 * HOUR
MID_WATER_SLOW = 30 * HOUR
SLOW_RATE = .5
LEGACY_SPECIES = ('daisy', 'tulip')
LEGACY_POT_FIELDS = ('planted', 'species', 'growth', 'duration', 'water_due', 'mist_due', 'mist_progress')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def empty_pot():
    return {
        'planted': False, 'plant_id': None, 'species': None,
        'growth': 0.0, 'duration': float(DAY),
        'initial_watered': False, 'care_elapsed': 0.0,
        'mid_watered': False, 'misted': False,
        'legacy_care_exempt': False, 'ruleset_id': None,
        'base_sale_g': 0, 'mist_bonus_g': 0,
        'care_profile': None, 'is_tutorial': False,
    }


POT_FIELDS = tuple(empty_pot())


@dataclass
class SingleGarden:
    """Legacy schema-two shape retained only for validated save migration."""
    CURRENT_SCHEMA: ClassVar[int] = 2

    last_update: float
    schema: int = CURRENT_SCHEMA
    planted: bool = False
    species: str | None = None
    growth: float = 0
    duration: float = DAY
    water_due: float = 0
    mist_due: float = 0
    mist_progress: int = 0
    tutorial_used: bool = False
    coins: int = 120
    seeds: dict = field(default_factory=lambda: {'daisy': 1, 'tulip': 0})
    collection: list = field(default_factory=list)
    vacation: bool = False
    settings: dict = field(default_factory=lambda: dict(opacity=1.0, topmost=True, x=-99999, y=-99999))

    @property
    def bloomed(self):
        return self.planted and self.growth >= self.duration

    def plant(self, now, species='daisy'):
        if species not in LEGACY_SPECIES or self.planted or self.vacation or self.seeds.get(species, 0) <= 0:
            return False
        if not self.tutorial_used and species != 'daisy':
            return False
        self.advance(now)
        self.seeds[species] -= 1
        self.planted, self.species, self.growth = True, species, 0
        self.duration = plant_definition(species).growth_seconds if self.tutorial_used else 60
        self.tutorial_used = True
        self.water_due = self.last_update + 2 * DAY
        self.mist_due = self.last_update + 2 * DAY
        self.mist_progress = 0
        return True

    def advance(self, now):
        if now <= self.last_update:
            return
        elapsed = 0 if self.vacation else min(now - self.last_update, OFFLINE_CAP)
        self.last_update = now
        if self.planted:
            self.growth = min(self.duration, self.growth + elapsed)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != set(cls(0).to_dict()):
            raise ValueError('저장 항목 오류')
        if type(data['schema']) is not int or data['schema'] != 2:
            raise ValueError('지원하지 않는 저장 버전')
        for key in ('last_update', 'growth', 'duration', 'water_due', 'mist_due'):
            if not _number(data[key]) or data[key] < 0:
                raise ValueError(key)
        if data['duration'] <= 0 or data['growth'] > data['duration']:
            raise ValueError('성장 범위')
        if data['species'] not in LEGACY_SPECIES and data['species'] is not None:
            raise ValueError('식물 종류')
        if data['planted'] != (data['species'] is not None):
            raise ValueError('식물 상태')
        for key in ('planted', 'tutorial_used', 'vacation'):
            if type(data[key]) is not bool:
                raise ValueError(key)
        if type(data['mist_progress']) is not int or data['mist_progress'] < 0:
            raise ValueError('분무 진행')
        if type(data['coins']) is not int or data['coins'] < 0:
            raise ValueError('coins')
        if not isinstance(data['seeds'], dict) or set(data['seeds']) != set(LEGACY_SPECIES):
            raise ValueError('씨앗')
        if any(type(value) is not int or value < 0 for value in data['seeds'].values()):
            raise ValueError('씨앗')
        _validate_legacy_collection(data['collection'])
        _validate_settings(data['settings'])
        return cls(**deepcopy(data))


def _validate_settings(settings):
    if (
        not isinstance(settings, dict)
        or set(settings) != {'opacity', 'topmost', 'x', 'y'}
        or type(settings['topmost']) is not bool
        or any(not _number(settings[key]) for key in ('opacity', 'x', 'y'))
        or not .1 <= settings['opacity'] <= 1
    ):
        raise ValueError('창 설정')


def _validate_legacy_collection(items):
    if not isinstance(items, list):
        raise ValueError('보관함')
    ids = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or set(item) != {'id', 'species', 'harvested_at'}
            or not isinstance(item['id'], str) or not item['id']
            or item['id'] in ids or item['species'] not in LEGACY_SPECIES
            or not _number(item['harvested_at']) or item['harvested_at'] < 0
        ):
            raise ValueError('보관 식물')
        ids.add(item['id'])


@dataclass
class Garden:
    """Shared inventory with one or two independently simulated pots."""
    CURRENT_SCHEMA: ClassVar[int] = 4

    last_update: float
    schema: int = CURRENT_SCHEMA
    tutorial_used: bool = False
    tutorial_reward_claimed: bool = False
    coins: int = 120
    seeds: dict = field(default_factory=lambda: {key: int(key == 'daisy') for key in PLANTS})
    collection: list = field(default_factory=list)
    vacation: bool = False
    settings: dict = field(default_factory=lambda: dict(opacity=1.0, topmost=True, x=-99999, y=-99999))
    pots: list = field(default_factory=list)
    selected: int = 0

    def __post_init__(self):
        if not self.pots:
            self.pots = [empty_pot()]

    @property
    def pot(self):
        return self.pots[self.selected]

    @property
    def planted(self):
        return self.pot['planted']

    @property
    def species(self):
        return self.pot['species']

    @property
    def growth(self):
        return self.pot['growth']

    @growth.setter
    def growth(self, value):
        self.pot['growth'] = value

    @property
    def duration(self):
        return self.pot['duration']

    @duration.setter
    def duration(self, value):
        self.pot['duration'] = value

    @property
    def definition(self):
        return plant_definition(self.species or 'daisy')

    @property
    def bloomed(self):
        return self.planted and self.growth >= self.duration

    @property
    def ratio(self):
        return self.growth / self.duration if self.planted and self.duration else 0

    @property
    def stage(self):
        return sum(self.ratio >= value for value in (.1, .35, .7, 1))

    @property
    def health(self):
        if self.vacation:
            return '휴가 중 · 성장과 돌봄이 멈춰요'
        if not self.planted:
            return '씨앗을 골라 하루를 시작해요'
        if self.bloomed:
            return f'{self.definition.name} 개화 완료 · 보관할 수 있어요'
        if not self.pot['initial_watered']:
            return '물을 주면 성장이 시작돼요'
        if self.water_status == 'slow':
            return '천천히 자라고 있어요 · 물을 주면 원래 속도로 돌아와요'
        if self.water_status == 'due':
            return '물주기를 권장해요 · 지금은 정상 속도로 자라고 있어요'
        if self.water_status == 'early':
            return '미리 물을 줄 수 있어요'
        return f'{self.definition.name}가 건강하게 자라고 있어요'

    @property
    def water_status(self):
        pot = self.pot
        if not pot['planted'] or self.bloomed:
            return 'unavailable'
        if not pot['initial_watered']:
            return 'initial'
        if pot['care_profile'] != 'tulip_midwater' or pot['legacy_care_exempt'] or pot['mid_watered']:
            return 'done'
        age = pot['care_elapsed']
        if age < MID_WATER_EARLY:
            return 'waiting'
        if age < MID_WATER_DUE:
            return 'early'
        if age < MID_WATER_SLOW:
            return 'due'
        return 'slow'

    def seed_count(self, species):
        return self.seeds.get(species, 0)

    def can_plant(self, species):
        if species not in PLANTS or self.planted or self.vacation:
            return False
        if not self.tutorial_used and species != 'daisy':
            return False
        return self.seed_count(species) > 0

    def select(self, index):
        if type(index) is not int or not 0 <= index < len(self.pots):
            return False
        self.selected = index
        return True

    @staticmethod
    def _advance_pot(pot, elapsed):
        if elapsed <= 0 or not pot['planted'] or not pot['initial_watered'] or pot['growth'] >= pot['duration']:
            return
        old_age = pot['care_elapsed']
        new_age = old_age + elapsed
        if pot['care_profile'] == 'tulip_midwater' and not pot['mid_watered'] and not pot['legacy_care_exempt']:
            normal = max(0.0, min(new_age, MID_WATER_SLOW) - min(old_age, MID_WATER_SLOW))
            slow = max(0.0, new_age - max(old_age, MID_WATER_SLOW))
            gained = normal + slow * SLOW_RATE
        else:
            gained = elapsed
        pot['care_elapsed'] = new_age
        pot['growth'] = min(pot['duration'], pot['growth'] + gained)

    def advance(self, now):
        if not _number(now) or now <= self.last_update:
            return
        elapsed = min(now - self.last_update, OFFLINE_CAP)
        self.last_update = now
        if self.vacation:
            return
        for pot in self.pots:
            self._advance_pot(pot, elapsed)

    def plant(self, now, species='daisy'):
        self.advance(now)
        if not self.can_plant(species):
            return False
        definition = plant_definition(species)
        is_tutorial = not self.tutorial_used
        self.seeds[species] -= 1
        self.pots[self.selected] = {
            'planted': True, 'plant_id': str(uuid4()), 'species': species,
            'growth': 0.0, 'duration': float(60 if is_tutorial else definition.growth_seconds),
            'initial_watered': False, 'care_elapsed': 0.0,
            'mid_watered': False, 'misted': False,
            'legacy_care_exempt': False, 'ruleset_id': 'v0.4',
            'base_sale_g': definition.sale_price,
            'mist_bonus_g': definition.mist_bonus,
            'care_profile': 'start_only' if is_tutorial else definition.care_profile,
            'is_tutorial': is_tutorial,
        }
        self.tutorial_used = True
        return True

    def care(self, kind, now):
        self.advance(now)
        if kind not in ('water', 'mist') or not self.planted or self.bloomed or self.vacation:
            return False
        pot = self.pot
        if kind == 'mist':
            if not pot['initial_watered'] or pot['misted']:
                return False
            pot['misted'] = True
            return True
        if not pot['initial_watered']:
            pot['initial_watered'] = True
            pot['care_elapsed'] = 0.0
            return True
        if self.water_status in ('early', 'due', 'slow'):
            pot['mid_watered'] = True
            return True
        return False

    def remaining_seconds(self, water_now=False):
        if not self.planted or self.bloomed:
            return 0
        pot = self.pot
        remaining = max(0.0, pot['duration'] - pot['growth'])
        if not pot['initial_watered']:
            return None
        if water_now or pot['care_profile'] != 'tulip_midwater' or pot['mid_watered'] or pot['legacy_care_exempt']:
            return remaining
        normal_window = max(0.0, MID_WATER_SLOW - pot['care_elapsed'])
        normal_growth = min(remaining, normal_window)
        return normal_growth + (remaining - normal_growth) / SLOW_RATE

    def harvest(self, now):
        self.advance(now)
        if not self.bloomed:
            return False
        pot = self.pot
        item = {
            'id': pot['plant_id'], 'species': pot['species'], 'harvested_at': self.last_update,
            'base_sale_g': pot['base_sale_g'], 'misted': pot['misted'],
            'bonus_g': pot['mist_bonus_g'] if pot['misted'] else 0,
        }
        if any(existing['id'] == item['id'] for existing in self.collection):
            return False
        self.collection.append(item)
        if pot['is_tutorial'] and not self.tutorial_reward_claimed:
            self.seeds[pot['species']] += 1
            self.tutorial_reward_claimed = True
        self.pots[self.selected] = empty_pot()
        return True

    def buy_seed(self, species='daisy'):
        if species not in PLANTS:
            return False
        price = plant_definition(species).seed_price
        if self.coins < price:
            return False
        self.coins -= price
        self.seeds[species] += 1
        return True

    def buy_pot(self):
        if len(self.pots) >= 2 or self.coins < 150:
            return False
        self.coins -= 150
        self.pots.append(empty_pot())
        return True

    def sell(self, item_id=None):
        if item_id is None and self.collection:
            item_id = self.collection[-1]['id']
        for index, item in enumerate(self.collection):
            if item['id'] == item_id:
                self.coins += item['base_sale_g'] + item['bonus_g']
                self.collection.pop(index)
                return True
        return False

    def set_vacation(self, enabled, now):
        if type(enabled) is not bool:
            return False
        self.advance(now)
        self.vacation = enabled
        return True

    def to_dict(self):
        return deepcopy(asdict(self))

    def restore(self, data):
        restored = self.from_dict(data)
        self.__dict__.clear()
        self.__dict__.update(restored.__dict__)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != set(cls(0).to_dict()):
            raise ValueError('저장 항목 오류')
        if type(data['schema']) is not int or data['schema'] != cls.CURRENT_SCHEMA:
            raise ValueError('지원하지 않는 저장 버전')
        if not _number(data['last_update']) or data['last_update'] < 0:
            raise ValueError('last_update')
        if type(data['coins']) is not int or data['coins'] < 0:
            raise ValueError('coins')
        for key in ('tutorial_used', 'tutorial_reward_claimed', 'vacation'):
            if type(data[key]) is not bool:
                raise ValueError(key)
        if data['tutorial_reward_claimed'] and not data['tutorial_used']:
            raise ValueError('첫 재배 보상')
        if not isinstance(data['seeds'], dict) or set(data['seeds']) != set(PLANTS):
            raise ValueError('씨앗')
        if any(type(value) is not int or value < 0 for value in data['seeds'].values()):
            raise ValueError('씨앗')
        _validate_settings(data['settings'])
        pots = data['pots']
        if not isinstance(pots, list) or not 1 <= len(pots) <= 2:
            raise ValueError('화분 개수')
        if type(data['selected']) is not int or not 0 <= data['selected'] < len(pots):
            raise ValueError('선택 화분')
        active_ids = set()
        for pot in pots:
            cls._validate_pot(pot)
            if pot['plant_id'] is not None:
                if pot['plant_id'] in active_ids:
                    raise ValueError('중복 재배 ID')
                active_ids.add(pot['plant_id'])
        collection_ids = cls._validate_collection(data['collection'])
        if active_ids & collection_ids:
            raise ValueError('중복 꽃 ID')
        return cls(**deepcopy(data))

    @staticmethod
    def _validate_pot(pot):
        if not isinstance(pot, dict) or set(pot) != set(POT_FIELDS):
            raise ValueError('화분 항목')
        for key in ('planted', 'initial_watered', 'mid_watered', 'misted', 'legacy_care_exempt', 'is_tutorial'):
            if type(pot[key]) is not bool:
                raise ValueError(key)
        for key in ('growth', 'duration', 'care_elapsed'):
            if not _number(pot[key]) or pot[key] < 0:
                raise ValueError(key)
        if pot['duration'] <= 0 or pot['growth'] > pot['duration']:
            raise ValueError('성장 범위')
        for key in ('base_sale_g', 'mist_bonus_g'):
            if type(pot[key]) is not int or pot[key] < 0:
                raise ValueError(key)
        if not pot['planted']:
            if pot != empty_pot():
                raise ValueError('빈 화분 상태')
            return
        if pot['species'] not in PLANTS or not isinstance(pot['plant_id'], str) or not pot['plant_id']:
            raise ValueError('재배 식별')
        if pot['ruleset_id'] not in ('v0.4', 'legacy-v3'):
            raise ValueError('재배 규칙')
        if pot['care_profile'] not in ('start_only', 'tulip_midwater'):
            raise ValueError('돌봄 규칙')
        if not pot['initial_watered'] and (pot['growth'] != 0 or pot['care_elapsed'] != 0 or pot['mid_watered'] or pot['misted']):
            raise ValueError('첫 물 전 상태')
        if pot['mid_watered'] and pot['care_profile'] != 'tulip_midwater':
            raise ValueError('중간 물 상태')

    @staticmethod
    def _validate_collection(items):
        if not isinstance(items, list):
            raise ValueError('보관함')
        ids = set()
        expected = {'id', 'species', 'harvested_at', 'base_sale_g', 'misted', 'bonus_g'}
        for item in items:
            if not isinstance(item, dict) or set(item) != expected:
                raise ValueError('보관 식물')
            if (
                not isinstance(item['id'], str) or not item['id'] or item['id'] in ids
                or item['species'] not in PLANTS
                or not _number(item['harvested_at']) or item['harvested_at'] < 0
                or type(item['base_sale_g']) is not int or item['base_sale_g'] < 0
                or type(item['misted']) is not bool
                or type(item['bonus_g']) is not int or item['bonus_g'] < 0
                or item['bonus_g'] > item['base_sale_g'] // 10
                or (not item['misted'] and item['bonus_g'] != 0)
            ):
                raise ValueError('보관 식물')
            ids.add(item['id'])
        return ids
