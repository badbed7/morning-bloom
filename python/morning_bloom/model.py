"""UI-independent real-time garden. Timestamps are UTC Unix seconds."""
from dataclasses import dataclass, field, asdict
from uuid import uuid4
import math

DAY = 86400

@dataclass
class Garden:
    last_update: float
    schema: int = 1
    planted: bool = False
    growth: float = 0
    duration: float = DAY
    water_due: float = 0
    mist_due: float = 0
    tutorial_used: bool = False
    coins: int = 120
    seeds: int = 1
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
    def health(self):
        if self.vacation: return '휴가 중 · 성장과 돌봄이 멈춰요'
        if not self.planted: return '씨앗을 심어 하루를 시작해요'
        if self.bloomed: return '개화 완료 · 보관할 수 있어요'
        late = self.last_update - min(self.water_due, self.mist_due)
        if late >= DAY: return '시듦 · 물과 분무로 무료 회복'
        if late > 0: return '돌봄이 필요해요'
        return '건강하게 자라고 있어요'

    def advance(self, now):
        if now <= self.last_update: return
        previous, elapsed = self.last_update, now - self.last_update
        self.last_update = now
        simulated = 0 if self.vacation else min(elapsed, 3 * DAY)
        healthy = max(0, min(previous + simulated, min(self.water_due, self.mist_due) + DAY) - previous)
        if self.planted and not self.bloomed:
            self.growth = min(self.duration, self.growth + healthy)
        self.water_due += elapsed - simulated
        self.mist_due += elapsed - simulated

    def plant(self, now):
        self.advance(now)
        if self.planted or self.vacation: return False
        if self.seeds: self.seeds -= 1
        elif self.coins >= 20: self.coins -= 20
        else: return False
        self.planted, self.growth = True, 0
        self.duration = DAY if self.tutorial_used else 60
        self.tutorial_used = True
        self.water_due = self.mist_due = self.last_update + 2 * DAY
        return True

    def care(self, kind, now):
        self.advance(now)
        if kind not in ('water', 'mist') or not self.planted or self.bloomed or self.vacation: return False
        key = kind + '_due'
        if getattr(self, key) - self.last_update <= 12 * 3600:
            setattr(self, key, self.last_update + 2 * DAY)
        return True

    def harvest(self, now):
        self.advance(now)
        if not self.bloomed: return False
        self.collection.append(dict(id=str(uuid4()), species='daisy', harvested_at=self.last_update))
        if self.duration == 60: self.seeds += 1
        self.planted, self.growth = False, 0
        return True

    def sell(self):
        if not self.collection: return False
        self.collection.pop()
        self.coins += 50
        return True

    def set_vacation(self, enabled, now):
        self.advance(now)
        self.vacation = enabled

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, data):
        def number(v): return type(v) in (int, float) and math.isfinite(v)
        if not isinstance(data, dict) or set(data) != set(cls(0).to_dict()): raise ValueError('저장 항목 오류')
        if type(data['schema']) is not int or data['schema'] != 1: raise ValueError('지원하지 않는 저장 버전')
        for key in ('last_update', 'growth', 'duration', 'water_due', 'mist_due', 'coins', 'seeds'):
            if not number(data[key]) or data[key] < 0: raise ValueError(key)
        for key in ('planted', 'tutorial_used', 'vacation'):
            if type(data[key]) is not bool: raise ValueError(key)
        if data['duration'] <= 0 or data['growth'] > data['duration']: raise ValueError('성장 범위')
        for key in ('coins', 'seeds'):
            if int(data[key]) != data[key]: raise ValueError(key)
        items = data['collection']
        if not isinstance(items, list): raise ValueError('보관함')
        ids = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in ids or item.get('species') != 'daisy' or not number(item.get('harvested_at')) or item['harvested_at'] < 0: raise ValueError('보관 식물')
            ids.add(item['id'])
        s = data['settings']
        if not isinstance(s, dict) or type(s.get('topmost')) is not bool or any(not number(s.get(k)) for k in ('opacity', 'x', 'y')) or not .1 <= s['opacity'] <= 1: raise ValueError('창 설정')
        result = cls(**data)
        result.coins, result.seeds = int(result.coins), int(result.seeds)
        return result
