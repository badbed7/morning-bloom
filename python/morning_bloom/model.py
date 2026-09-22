"""UI-independent real-time garden. Timestamps are UTC Unix seconds."""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import ClassVar
from uuid import uuid4
import math
import secrets

from .cosmetics import POT_SKINS, THEMES, garden_theme, pot_skin
from .plant_catalog import DAY, HOUR, PLANTS, REGULAR_PLANTS, RANDOM_SEED_PRICE, plant_definition, roll_mystery_seed

OFFLINE_CAP = 3 * DAY
MID_WATER_EARLY = 22 * HOUR
MID_WATER_DUE = 24 * HOUR
MID_WATER_SLOW = 30 * HOUR
SLOW_RATE = .5
SUN_INTERVAL = 20 * 60
SUN_PENDING_CAP = 9
POT_PRICES = (0, 150, 200, 300)
TYCOON_RULE = 'tycoon-v1'
WATER_INTERVAL = 30 * 60
MIST_INTERVAL = 15 * 60
FERTILIZER_SECONDS = 10 * 60
FERTILIZER_CAP = 5
REWARD_INTERVAL = 3 * 60
V8_FIELDS = {'fertilizer_reserve', 'mystery_seeds', 'mystery_plants', 'desktop_flowers', 'desktop_opacity'}
TYCOON_POT_DEFAULTS = dict(water_wait=0.0, mist_wait=0.0, water_count=0,
                           mist_count=0, fertilizer_used=0, fertilizer_limit=0)
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
        **TYCOON_POT_DEFAULTS,
    }


POT_FIELDS = tuple(empty_pot())


def growth_stage(pot):
    ratio = pot['growth'] / pot['duration'] if pot['planted'] else 0
    return sum(ratio >= value for value in (.1, .35, .7, 1))


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
    """Shared inventory with up to four independently simulated pots."""
    CURRENT_SCHEMA: ClassVar[int] = 9

    last_update: float
    schema: int = CURRENT_SCHEMA
    tutorial_used: bool = False
    tutorial_reward_claimed: bool = False
    coins: int = 120
    seeds: dict = field(default_factory=lambda: {key: int(key == 'daisy') for key in REGULAR_PLANTS})
    mystery_seeds: list = field(default_factory=list)
    mystery_plants: list = field(default_factory=list)
    desktop_flowers: dict = field(default_factory=dict)
    desktop_opacity: float = 1.0
    collection: list = field(default_factory=list)
    sunlight: int = 0
    sun_tokens: list = field(default_factory=list)
    sun_elapsed: float = 0.0
    sun_cursor: int = 0
    sun_intro_claimed: bool = False
    owned_themes: list = field(default_factory=lambda: ['grass'])
    equipped_theme: str = 'grass'
    owned_skins: list = field(default_factory=lambda: ['terracotta'])
    equipped_skin: str = 'terracotta'
    fertilizer: int = 0
    fertilizer_reserve: int = 0
    reward_wait: float = 0.0
    last_reward_id: str | None = None
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
    def mystery_hidden(self):
        return self.pot['plant_id'] in self.mystery_plants and not self.bloomed

    @property
    def display_name(self):
        return '신비한 식물' if self.mystery_hidden else self.definition.name

    @property
    def bloomed(self):
        return self.planted and self.growth >= self.duration

    @property
    def ratio(self):
        return self.growth / self.duration if self.planted and self.duration else 0

    @property
    def stage(self):
        return growth_stage(self.pot)

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
        return f'{self.display_name}이 건강하게 자라고 있어요'

    @property
    def water_status(self):
        return self.care_status('water')

    def care_status(self, kind, pot=None):
        pot = self.pot if pot is None else pot
        if kind not in ('water', 'mist') or not pot['planted'] or pot['growth'] >= pot['duration']:
            return 'unavailable'
        if not pot['initial_watered']:
            return 'initial' if kind == 'water' else 'unavailable'
        if pot['ruleset_id'] == TYCOON_RULE:
            if pot['is_tutorial'] or not self.tutorial_reward_claimed:
                return 'done' if kind == 'water' else 'unavailable'
            return 'waiting' if pot[kind + '_wait'] > 0 else 'ready'
        if kind == 'mist':
            return 'done' if pot['misted'] else 'ready'
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

    def can_care(self, kind):
        return not self.vacation and self.care_status(kind) in ('initial', 'ready', 'early', 'due', 'slow')

    @property
    def next_pot_price(self):
        return POT_PRICES[len(self.pots)] if len(self.pots) < len(POT_PRICES) else None

    @property
    def can_reward_fertilizer(self):
        return (self.tutorial_reward_claimed and not self.vacation
                and self.fertilizer < FERTILIZER_CAP and self.reward_wait <= 0)

    @property
    def can_use_fertilizer(self):
        return (self.tutorial_reward_claimed and not self.vacation and self.fertilizer > 0
                and self.planted and not self.bloomed and self.pot['initial_watered']
                and self.pot['ruleset_id'] == TYCOON_RULE and not self.pot['is_tutorial']
                and self.pot['fertilizer_used'] < self.pot['fertilizer_limit'])

    def use_fertilizer(self, now):
        self.advance(now)
        if not self.can_use_fertilizer:
            return False
        self.fertilizer -= 1
        if self.fertilizer_reserve:
            self.fertilizer_reserve -= 1
            self.fertilizer += 1
        self.pot['fertilizer_used'] += 1
        self.growth = min(self.duration, self.growth + FERTILIZER_SECONDS)
        return True

    def reward_fertilizer(self, game_id, now):
        self.advance(now)
        if (not isinstance(game_id, str) or not game_id or len(game_id) > 128
                or game_id == self.last_reward_id or not self.can_reward_fertilizer):
            return False
        self.fertilizer += 1
        self.reward_wait = float(REWARD_INTERVAL)
        self.last_reward_id = game_id
        return True

    def seed_count(self, species):
        if species == 'random':
            return len(self.mystery_seeds)
        return self.seeds.get(species, 0)

    def can_plant(self, species):
        if species not in (*REGULAR_PLANTS, 'random') or self.planted or self.vacation:
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
        if pot['ruleset_id'] == TYCOON_RULE and pot['initial_watered']:
            for key in ('water_wait', 'mist_wait'):
                pot[key] = max(0.0, pot[key] - elapsed)
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
        self.reward_wait = max(0.0, self.reward_wait - elapsed)
        for pot in self.pots:
            self._advance_pot(pot, elapsed)
        self._advance_sunlight(elapsed, now)

    def _advance_sunlight(self, elapsed, now):
        if not self.collection:
            self.sun_elapsed = 0.0
            return
        total = self.sun_elapsed + elapsed
        rounds = int(total // SUN_INTERVAL)
        self.sun_elapsed = total % SUN_INTERVAL
        if rounds <= 0 or len(self.sun_tokens) >= SUN_PENDING_CAP:
            return
        available = SUN_PENDING_CAP - len(self.sun_tokens)
        count = min(available, rounds * len(self.collection))
        for offset in range(count):
            source = self.collection[(self.sun_cursor + offset) % len(self.collection)]
            self.sun_tokens.append({
                'id': str(uuid4()),
                'source_flower_id': source['id'],
                'created_at': float(now),
            })
        self.sun_cursor = (self.sun_cursor + count) % len(self.collection)

    @property
    def seconds_to_sun(self):
        if self.vacation or not self.collection or len(self.sun_tokens) >= SUN_PENDING_CAP:
            return None
        return SUN_INTERVAL - self.sun_elapsed

    def plant(self, now, species='daisy'):
        self.advance(now)
        if not self.can_plant(species):
            return False
        mystery = species == 'random'
        if mystery:
            species = self.mystery_seeds.pop(0)
        else:
            self.seeds[species] -= 1
        definition = plant_definition(species)
        is_tutorial = not self.tutorial_used
        self.pots[self.selected] = {
            'planted': True, 'plant_id': str(uuid4()), 'species': species,
            'growth': 0.0, 'duration': float(60 if is_tutorial else definition.growth_seconds),
            'initial_watered': False, 'care_elapsed': 0.0,
            'mid_watered': False, 'misted': False,
            'legacy_care_exempt': False, 'ruleset_id': TYCOON_RULE,
            'base_sale_g': definition.sale_price,
            'mist_bonus_g': definition.mist_bonus,
            'care_profile': 'start_only' if is_tutorial else 'repeat',
            'is_tutorial': is_tutorial,
            **TYCOON_POT_DEFAULTS,
            'fertilizer_limit': 0 if is_tutorial else definition.growth_seconds // 2400,
        }
        if mystery:
            self.mystery_plants.append(self.pot['plant_id'])
        self.tutorial_used = True
        return True

    def care(self, kind, now):
        self.advance(now)
        if not self.can_care(kind):
            return False
        pot = self.pot
        if pot['ruleset_id'] == TYCOON_RULE:
            if kind == 'water' and not pot['initial_watered']:
                pot['initial_watered'] = True
                pot['care_elapsed'] = 0.0
                pot['water_count'] = 1
                pot['water_wait'] = 0.0 if pot['is_tutorial'] else float(WATER_INTERVAL)
                return True
            pot[kind + '_count'] += 1
            pot[kind + '_wait'] = float(WATER_INTERVAL if kind == 'water' else MIST_INTERVAL)
            self.growth = min(self.duration, self.growth + (180 if kind == 'water' else 60))
            if kind == 'mist':
                pot['misted'] = True
            return True
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
        was_empty = not self.collection
        self.collection.append(item)
        if item['id'] in self.mystery_plants:
            self.mystery_plants.remove(item['id'])
        if was_empty:
            self.sun_elapsed = 0.0
        if not self.sun_intro_claimed and len(self.sun_tokens) < SUN_PENDING_CAP:
            self.sun_tokens.append({
                'id': str(uuid4()),
                'source_flower_id': item['id'],
                'created_at': float(self.last_update),
            })
            self.sun_intro_claimed = True
        if pot['is_tutorial'] and not self.tutorial_reward_claimed:
            self.seeds[pot['species']] += 1
            self.tutorial_reward_claimed = True
        self.pots[self.selected] = empty_pot()
        return True

    def buy_seed(self, species='daisy'):
        if species not in (*REGULAR_PLANTS, 'random'):
            return False
        price = RANDOM_SEED_PRICE if species == 'random' else plant_definition(species).seed_price
        if self.coins < price:
            return False
        self.coins -= price
        if species == 'random':
            self.mystery_seeds.append(roll_mystery_seed(secrets.randbelow))
        else:
            self.seeds[species] += 1
        return True

    def desktop_source(self, item_id):
        for pot in self.pots:
            if pot['planted'] and pot['plant_id'] == item_id:
                return pot
        return next((item for item in self.collection if item['id'] == item_id), None)

    def place_desktop(self, item_id, x, y):
        if self.desktop_source(item_id) is None or not _number(x) or not _number(y):
            return False
        self.desktop_flowers[item_id] = {'x': round(x), 'y': round(y)}
        return True

    def return_desktop(self, item_id):
        return self.desktop_flowers.pop(item_id, None) is not None

    def set_desktop_opacity(self, value):
        if not _number(value) or not .1 <= value <= 1:
            return False
        self.desktop_opacity = value
        return True

    def buy_pot(self):
        price = self.next_pot_price
        if price is None or self.coins < price:
            return False
        self.coins -= price
        self.pots.append(empty_pot())
        return True

    def sell(self, item_id=None, now=None):
        if now is not None:
            self.advance(now)
        if item_id is None and self.collection:
            item_id = self.collection[-1]['id']
        for index, item in enumerate(self.collection):
            if item['id'] == item_id:
                self.coins += item['base_sale_g'] + item['bonus_g']
                self.collection.pop(index)
                self.desktop_flowers.pop(item_id, None)
                if not self.collection:
                    self.sun_elapsed = 0.0
                return True
        return False

    def collect_sun(self, token_id, now=None):
        if now is not None:
            self.advance(now)
        for index, token in enumerate(self.sun_tokens):
            if token['id'] == token_id:
                self.sun_tokens.pop(index)
                self.sunlight += 1
                return True
        return False

    def buy_theme(self, theme_id):
        if theme_id not in THEMES or theme_id in self.owned_themes:
            return False
        price = garden_theme(theme_id).price
        if self.sunlight < price:
            return False
        self.sunlight -= price
        self.owned_themes.append(theme_id)
        return True

    def equip_theme(self, theme_id):
        if theme_id not in self.owned_themes or theme_id not in THEMES:
            return False
        self.equipped_theme = theme_id
        return True

    def buy_skin(self, skin_id):
        if type(skin_id) is not str or skin_id not in POT_SKINS or skin_id in self.owned_skins:
            return False
        price = pot_skin(skin_id).price
        if self.sunlight < price:
            return False
        self.sunlight -= price
        self.owned_skins.append(skin_id)
        return True

    def equip_skin(self, skin_id):
        if type(skin_id) is not str or skin_id not in self.owned_skins or skin_id not in POT_SKINS:
            return False
        self.equipped_skin = skin_id
        return True

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
        for key in ('tutorial_used', 'tutorial_reward_claimed', 'sun_intro_claimed', 'vacation'):
            if type(data[key]) is not bool:
                raise ValueError(key)
        if data['tutorial_reward_claimed'] and not data['tutorial_used']:
            raise ValueError('첫 재배 보상')
        if not isinstance(data['seeds'], dict) or set(data['seeds']) != set(REGULAR_PLANTS):
            raise ValueError('씨앗')
        if any(type(value) is not int or value < 0 for value in data['seeds'].values()):
            raise ValueError('씨앗')
        if type(data['sunlight']) is not int or data['sunlight'] < 0:
            raise ValueError('햇빛')
        if type(data['fertilizer']) is not int or not 0 <= data['fertilizer'] <= FERTILIZER_CAP:
            raise ValueError('비료 재고')
        if type(data['fertilizer_reserve']) is not int or not 0 <= data['fertilizer_reserve'] <= 5:
            raise ValueError('이전 비료 예비 재고')
        if data['fertilizer_reserve'] and data['fertilizer'] != FERTILIZER_CAP:
            raise ValueError('예비 비료는 사용 시 자동 보충')
        if (not isinstance(data['mystery_seeds'], list)
                or any(type(key) is not str or key not in PLANTS for key in data['mystery_seeds'])):
            raise ValueError('랜덤 씨앗')
        if (not isinstance(data['mystery_plants'], list)
                or any(type(key) is not str for key in data['mystery_plants'])
                or len(set(data['mystery_plants'])) != len(data['mystery_plants'])):
            raise ValueError('랜덤 재배 식별')
        if not _number(data['desktop_opacity']) or not .1 <= data['desktop_opacity'] <= 1:
            raise ValueError('바탕화면 꽃 불투명도')
        if not _number(data['reward_wait']) or not 0 <= data['reward_wait'] <= REWARD_INTERVAL:
            raise ValueError('비료 보상 대기')
        if data['last_reward_id'] is not None and (
            not isinstance(data['last_reward_id'], str) or not 1 <= len(data['last_reward_id']) <= 128
        ):
            raise ValueError('비료 지급 기록')
        if data['reward_wait'] > 0 and data['last_reward_id'] is None:
            raise ValueError('비료 지급 기록 없음')
        if not _number(data['sun_elapsed']) or not 0 <= data['sun_elapsed'] < SUN_INTERVAL:
            raise ValueError('햇빛 생산 시간')
        if type(data['sun_cursor']) is not int or data['sun_cursor'] < 0:
            raise ValueError('햇빛 생산 순번')
        cls._validate_sun_tokens(data['sun_tokens'])
        owned = data['owned_themes']
        if (
            not isinstance(owned, list) or not owned
            or any(type(key) is not str or key not in THEMES for key in owned)
            or len(owned) != len(set(owned)) or 'grass' not in owned
            or type(data['equipped_theme']) is not str or data['equipped_theme'] not in owned
        ):
            raise ValueError('정원 꾸미기')
        owned = data['owned_skins']
        if (
            not isinstance(owned, list) or not owned
            or any(type(key) is not str or key not in POT_SKINS for key in owned)
            or len(owned) != len(set(owned)) or 'terracotta' not in owned
            or type(data['equipped_skin']) is not str or data['equipped_skin'] not in owned
        ):
            raise ValueError('화분 스킨')
        _validate_settings(data['settings'])
        pots = data['pots']
        if not isinstance(pots, list) or not 1 <= len(pots) <= len(POT_PRICES):
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
        if not set(data['mystery_plants']) <= active_ids:
            raise ValueError('존재하지 않는 랜덤 재배')
        if (not isinstance(data['desktop_flowers'], dict)
                or not set(data['desktop_flowers']) <= collection_ids | active_ids):
            raise ValueError('바탕화면 꽃 식별')
        for position in data['desktop_flowers'].values():
            if (not isinstance(position, dict) or set(position) != {'x', 'y'}
                    or any(not _number(v) or abs(v) > 100000 for v in position.values())):
                raise ValueError('바탕화면 꽃 위치')
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
        for key, maximum in (('water_wait', WATER_INTERVAL), ('mist_wait', MIST_INTERVAL)):
            if not _number(pot[key]) or not 0 <= pot[key] <= maximum:
                raise ValueError('돌봄 대기시간')
        for key in ('water_count', 'mist_count', 'fertilizer_used', 'fertilizer_limit'):
            if type(pot[key]) is not int or pot[key] < 0:
                raise ValueError('돌봄 사용 횟수')
        if pot['fertilizer_used'] > pot['fertilizer_limit'] or pot['fertilizer_limit'] * 600 > pot['duration'] * .25:
            raise ValueError('비료 사용 상한')
        if not pot['planted']:
            if pot != empty_pot():
                raise ValueError('빈 화분 상태')
            return
        if pot['species'] not in PLANTS or not isinstance(pot['plant_id'], str) or not pot['plant_id']:
            raise ValueError('재배 식별')
        if pot['ruleset_id'] not in ('v0.4', 'legacy-v3', TYCOON_RULE):
            raise ValueError('재배 규칙')
        if pot['care_profile'] not in ('start_only', 'tulip_midwater', 'repeat'):
            raise ValueError('돌봄 규칙')
        if not pot['initial_watered'] and (pot['growth'] != 0 or pot['care_elapsed'] != 0 or pot['mid_watered'] or pot['misted']):
            raise ValueError('첫 물 전 상태')
        if pot['mid_watered'] and pot['care_profile'] != 'tulip_midwater':
            raise ValueError('중간 물 상태')
        if pot['ruleset_id'] != TYCOON_RULE:
            if pot['care_profile'] == 'repeat' or any(pot[key] != value for key, value in TYCOON_POT_DEFAULTS.items()):
                raise ValueError('기존 작물 돌봄 상태')
        else:
            if pot['care_profile'] != ('start_only' if pot['is_tutorial'] else 'repeat') or pot['legacy_care_exempt']:
                raise ValueError('새 작물 돌봄 규칙')
            if not pot['initial_watered'] and any(pot[key] for key in TYCOON_POT_DEFAULTS if key != 'fertilizer_limit'):
                raise ValueError('첫 물 전 돌봄 상태')
            if pot['initial_watered'] != (pot['water_count'] > 0) or pot['misted'] != (pot['mist_count'] > 0):
                raise ValueError('돌봄 횟수와 상태 불일치')
            if pot['is_tutorial'] and (pot['misted'] or pot['fertilizer_limit'] or pot['water_count'] > 1):
                raise ValueError('첫 꽃 돌봄 상태')

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

    @staticmethod
    def _validate_sun_tokens(tokens):
        if not isinstance(tokens, list) or len(tokens) > SUN_PENDING_CAP:
            raise ValueError('대기 햇빛')
        ids = set()
        expected = {'id', 'source_flower_id', 'created_at'}
        for token in tokens:
            if (
                not isinstance(token, dict) or set(token) != expected
                or not isinstance(token['id'], str) or not token['id'] or token['id'] in ids
                or not isinstance(token['source_flower_id'], str) or not token['source_flower_id']
                or not _number(token['created_at']) or token['created_at'] < 0
            ):
                raise ValueError('대기 햇빛')
            ids.add(token['id'])
