"""UI-independent real-time garden. Timestamps are UTC Unix seconds."""
from dataclasses import asdict, dataclass, field
from typing import ClassVar
from uuid import uuid4
import math

from .plant_catalog import DAY, PLANTS, plant_definition


@dataclass
class SingleGarden:
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
    seeds: dict = field(default_factory=lambda: {key: int(key == 'daisy') for key in PLANTS})
    collection: list = field(default_factory=list)
    vacation: bool = False
    settings: dict = field(default_factory=lambda: dict(opacity=1.0, topmost=True, x=-99999, y=-99999))

    @property
    def bloomed(self):
        return self.planted and self.growth >= self.duration

    @property
    def ratio(self):
        return self.growth / self.duration if self.planted else 0

    @property
    def stage(self):
        return sum(self.ratio >= n for n in (.1, .35, .7, 1))

    @property
    def definition(self):
        return plant_definition(self.species or 'daisy')

    @property
    def health(self):
        if self.vacation:
            return '휴가 중 · 성장과 돌봄이 멈춰요'
        if not self.planted:
            return '씨앗을 골라 하루를 시작해요'
        if self.bloomed:
            return f'{self.definition.name} 개화 완료 · 보관할 수 있어요'
        late = self.last_update - min(self.water_due, self.mist_due)
        if late >= DAY:
            return '시듦 · 물과 분무로 무료 회복'
        if late > 0:
            return '돌봄이 필요해요'
        return f'{self.definition.name}가 건강하게 자라고 있어요'

    def seed_count(self, species):
        return self.seeds.get(species, 0)

    def can_plant(self, species):
        if species not in PLANTS or self.planted or self.vacation:
            return False
        if not self.tutorial_used and species != 'daisy':
            return False
        definition = plant_definition(species)
        return self.seed_count(species) > 0 or self.coins >= definition.seed_price

    def advance(self, now):
        if now <= self.last_update:
            return
        previous, elapsed = self.last_update, now - self.last_update
        self.last_update = now
        simulated = 0 if self.vacation else min(elapsed, 3 * DAY)
        healthy = max(0, min(previous + simulated, min(self.water_due, self.mist_due) + DAY) - previous)
        if self.planted and not self.bloomed:
            self.growth = min(self.duration, self.growth + healthy)
        self.water_due += elapsed - simulated
        self.mist_due += elapsed - simulated

    def plant(self, now, species='daisy'):
        self.advance(now)
        if not self.can_plant(species):
            return False
        definition = plant_definition(species)
        if self.seed_count(species):
            self.seeds[species] -= 1
        else:
            self.coins -= definition.seed_price
        self.planted, self.species, self.growth = True, species, 0
        self.duration = definition.growth_seconds if self.tutorial_used else 60
        self.tutorial_used = True
        self.water_due = self.last_update + definition.water_interval
        self.mist_due = self.last_update + definition.mist_interval
        self.mist_progress = 0
        return True

    def care(self, kind, now):
        self.advance(now)
        if kind not in ('water', 'mist') or not self.planted or self.bloomed or self.vacation:
            return False
        definition = self.definition
        key = kind + '_due'
        if getattr(self, key) - self.last_update <= 12 * 3600:
            if kind == 'mist':
                self.mist_progress += 1
                if self.mist_progress < definition.mist_actions:
                    return True
                self.mist_progress = 0
                interval = definition.mist_interval
            else:
                interval = definition.water_interval
            setattr(self, key, self.last_update + interval)
        return True

    def harvest(self, now):
        self.advance(now)
        if not self.bloomed:
            return False
        harvested_species = self.species
        self.collection.append(dict(id=str(uuid4()), species=harvested_species, harvested_at=self.last_update))
        if self.duration == 60:
            self.seeds[harvested_species] += 1
        self.planted, self.species, self.growth = False, None, 0
        self.mist_progress = 0
        return True

    def sell(self):
        if not self.collection:
            return False
        item = self.collection.pop()
        self.coins += plant_definition(item['species']).sale_price
        return True

    def set_vacation(self, enabled, now):
        self.advance(now)
        self.vacation = enabled

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        def number(value):
            return type(value) in (int, float) and math.isfinite(value)

        if not isinstance(data, dict) or set(data) != set(cls(0).to_dict()):
            raise ValueError('저장 항목 오류')
        if type(data['schema']) is not int or data['schema'] != cls.CURRENT_SCHEMA:
            raise ValueError('지원하지 않는 저장 버전')
        for key in ('last_update', 'growth', 'duration', 'water_due', 'mist_due', 'coins'):
            if not number(data[key]) or data[key] < 0:
                raise ValueError(key)
        for key in ('planted', 'tutorial_used', 'vacation'):
            if type(data[key]) is not bool:
                raise ValueError(key)
        if data['duration'] <= 0 or data['growth'] > data['duration']:
            raise ValueError('성장 범위')
        if data['species'] not in PLANTS and data['species'] is not None:
            raise ValueError('식물 종류')
        if data['planted'] != (data['species'] is not None):
            raise ValueError('식물 상태')
        if type(data['mist_progress']) is not int or data['mist_progress'] < 0:
            raise ValueError('분무 진행')
        if int(data['coins']) != data['coins']:
            raise ValueError('coins')
        seeds = data['seeds']
        if not isinstance(seeds, dict) or set(seeds) != set(PLANTS):
            raise ValueError('씨앗')
        if any(type(count) is not int or count < 0 for count in seeds.values()):
            raise ValueError('씨앗')
        items = data['collection']
        if not isinstance(items, list):
            raise ValueError('보관함')
        ids = set()
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get('id'), str)
                or item['id'] in ids
                or item.get('species') not in PLANTS
                or not number(item.get('harvested_at'))
                or item['harvested_at'] < 0
            ):
                raise ValueError('보관 식물')
            ids.add(item['id'])
        settings = data['settings']
        if (
            not isinstance(settings, dict)
            or type(settings.get('topmost')) is not bool
            or any(not number(settings.get(key)) for key in ('opacity', 'x', 'y'))
            or not .1 <= settings['opacity'] <= 1
        ):
            raise ValueError('창 설정')
        result = cls(**data)
        result.coins = int(result.coins)
        return result



POT_FIELDS = ('planted', 'species', 'growth', 'duration', 'water_due', 'mist_due', 'mist_progress')

@dataclass
class Garden(SingleGarden):
    """Shared inventory with a selected pot; all pots advance on the same clock."""
    CURRENT_SCHEMA: ClassVar[int] = 3
    schema: int = 3
    pots: list = field(default_factory=list)
    selected: int = 0

    def __post_init__(self):
        if not self.pots:
            self.pots = [self._snapshot()]

    def _snapshot(self):
        return {key: getattr(self, key) for key in POT_FIELDS}

    def _save_active(self):
        self.pots[self.selected] = self._snapshot()

    def _load_pot(self, index):
        self.selected = index
        for key, value in self.pots[index].items():
            setattr(self, key, value)

    def select(self, index):
        if type(index) is not int or not 0 <= index < len(self.pots):
            return False
        self._save_active()
        self._load_pot(index)
        return True

    def advance(self, now):
        if now <= self.last_update:
            return
        self._save_active()
        previous, selected = self.last_update, self.selected
        for index in range(len(self.pots)):
            self._load_pot(index)
            self.last_update = previous
            SingleGarden.advance(self, now)
            self._save_active()
        self._load_pot(selected)

    def can_plant(self, species):
        return SingleGarden.can_plant(self, species) and self.seed_count(species) > 0

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
        self._save_active()
        self.coins -= 150
        empty = SingleGarden(self.last_update)
        self.pots.append({key: getattr(empty, key) for key in POT_FIELDS})
        return True

    def sell(self, item_id=None):
        # Retain the old API for callers; UI always supplies the selected ID.
        if item_id is None and self.collection:
            item_id = self.collection[-1]['id']
        for index, item in enumerate(self.collection):
            if item['id'] == item_id:
                self.coins += plant_definition(item['species']).sale_price
                self.collection.pop(index)
                return True
        return False

    def to_dict(self):
        self._save_active()
        data = asdict(self)
        for key in POT_FIELDS:
            data.pop(key)
        return data

    @classmethod
    def from_dict(cls, data):
        from copy import deepcopy
        if not isinstance(data, dict) or set(data) != set(cls(0).to_dict()):
            raise ValueError('저장 항목 오류')
        data = deepcopy(data)
        if type(data['schema']) is not int or data['schema'] != 3:
            raise ValueError('지원하지 않는 저장 버전')
        pots, selected = data['pots'], data['selected']
        if not isinstance(pots, list) or not 1 <= len(pots) <= 2:
            raise ValueError('화분 개수')
        if type(selected) is not int or not 0 <= selected < len(pots):
            raise ValueError('선택 화분')
        shared = {key: value for key, value in data.items() if key not in ('pots', 'selected')}
        for pot in pots:
            if not isinstance(pot, dict) or set(pot) != set(POT_FIELDS):
                raise ValueError('화분 항목')
            SingleGarden.from_dict({**shared, **pot, 'schema': 2})
        return cls(**data, **pots[selected])
