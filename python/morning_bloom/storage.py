"""Atomic saves; malformed or future-version files are never overwritten."""
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .model import (
    Garden,
    LEGACY_POT_FIELDS,
    LEGACY_SPECIES,
    SingleGarden,
    TYCOON_POT_DEFAULTS,
    V8_FIELDS,
    _number,
    _validate_legacy_collection,
    _validate_settings,
    empty_pot,
)
from .plant_catalog import REGULAR_PLANTS, plant_definition


class SaveError(Exception):
    pass


def _validate_v3(data):
    expected = {
        'last_update', 'schema', 'tutorial_used', 'coins', 'seeds',
        'collection', 'vacation', 'settings', 'pots', 'selected',
    }
    if not isinstance(data, dict) or set(data) != expected or data.get('schema') != 3:
        raise ValueError('v3 저장 항목 오류')
    if not _number(data['last_update']) or data['last_update'] < 0:
        raise ValueError('last_update')
    if type(data['tutorial_used']) is not bool or type(data['vacation']) is not bool:
        raise ValueError('상태 값')
    if type(data['coins']) is not int or data['coins'] < 0:
        raise ValueError('coins')
    if not isinstance(data['seeds'], dict) or set(data['seeds']) != set(LEGACY_SPECIES):
        raise ValueError('씨앗')
    if any(type(value) is not int or value < 0 for value in data['seeds'].values()):
        raise ValueError('씨앗')
    _validate_legacy_collection(data['collection'])
    _validate_settings(data['settings'])
    if not isinstance(data['pots'], list) or not 1 <= len(data['pots']) <= 2:
        raise ValueError('화분 개수')
    if type(data['selected']) is not int or not 0 <= data['selected'] < len(data['pots']):
        raise ValueError('선택 화분')
    for pot in data['pots']:
        if not isinstance(pot, dict) or set(pot) != set(LEGACY_POT_FIELDS):
            raise ValueError('화분 항목')
        SingleGarden.from_dict({
            'last_update': data['last_update'], 'schema': 2,
            **deepcopy(pot), 'tutorial_used': data['tutorial_used'],
            'coins': data['coins'], 'seeds': deepcopy(data['seeds']),
            'collection': deepcopy(data['collection']), 'vacation': data['vacation'],
            'settings': deepcopy(data['settings']),
        })


def _v2_to_v3(data):
    SingleGarden.from_dict(data)
    migrated = deepcopy(data)
    pot = {key: migrated.pop(key) for key in LEGACY_POT_FIELDS}
    migrated.update(schema=3, pots=[pot], selected=0)
    return migrated


def _stable_legacy_id(index, pot, last_update):
    source = f'morning-bloom:v3:{index}:{pot["species"]}:{last_update}:{pot["growth"]}'
    return str(uuid5(NAMESPACE_URL, source))


def _v3_to_v4(data):
    _validate_v3(data)
    migrated = {
        'last_update': data['last_update'], 'schema': 4,
        'tutorial_used': data['tutorial_used'],
        'tutorial_reward_claimed': data['tutorial_used'],
        'coins': data['coins'],
        'seeds': {key: data['seeds'].get(key, 0) for key in REGULAR_PLANTS},
        'collection': [], 'vacation': data['vacation'],
        'settings': deepcopy(data['settings']), 'pots': [],
        'selected': data['selected'],
    }
    for item in data['collection']:
        migrated['collection'].append({
            **deepcopy(item),
            'base_sale_g': plant_definition(item['species']).sale_price,
            'misted': False,
            'bonus_g': 0,
        })
    for index, legacy in enumerate(data['pots']):
        if not legacy['planted']:
            migrated['pots'].append({key: value for key, value in empty_pot().items()
                                     if key not in TYCOON_POT_DEFAULTS})
            continue
        definition = plant_definition(legacy['species'])
        is_tutorial = legacy['duration'] == 60
        migrated['pots'].append({
            'planted': True,
            'plant_id': _stable_legacy_id(index, legacy, data['last_update']),
            'species': legacy['species'],
            'growth': float(legacy['growth']),
            'duration': float(legacy['duration']),
            'initial_watered': True,
            'care_elapsed': float(legacy['growth']),
            'mid_watered': False,
            'misted': False,
            'legacy_care_exempt': True,
            'ruleset_id': 'legacy-v3',
            'base_sale_g': definition.sale_price,
            'mist_bonus_g': definition.mist_bonus,
            'care_profile': 'start_only' if is_tutorial else definition.care_profile,
            'is_tutorial': is_tutorial,
        })
        if is_tutorial:
            migrated['tutorial_reward_claimed'] = False
    return migrated


def _v4_to_v5(data):
    expected = {
        'last_update', 'schema', 'tutorial_used', 'tutorial_reward_claimed',
        'coins', 'seeds', 'collection', 'vacation', 'settings', 'pots', 'selected',
    }
    if not isinstance(data, dict) or set(data) != expected or data.get('schema') != 4:
        raise ValueError('v4 저장 항목 오류')
    migrated = deepcopy(data)
    migrated.update(
        schema=5,
        sunlight=0,
        sun_tokens=[],
        sun_elapsed=0.0,
        sun_cursor=0,
        sun_intro_claimed=False,
        owned_themes=['grass'],
        equipped_theme='grass',
    )
    _v5_to_v6(migrated)
    if migrated['collection']:
        first = migrated['collection'][0]
        migrated['sun_tokens'] = [{
            'id': str(uuid5(NAMESPACE_URL, f'morning-bloom:v5:sun-intro:{first["id"]}')),
            'source_flower_id': first['id'],
            'created_at': float(migrated['last_update']),
        }]
        migrated['sun_intro_claimed'] = True
        _v5_to_v6(migrated)
    return migrated


def _v5_to_v6(data):
    expected = set(Garden(0).to_dict()) - V8_FIELDS - {'fertilizer', 'reward_wait', 'last_reward_id', 'owned_skins', 'equipped_skin'}
    old_pot_fields = set(empty_pot()) - set(TYCOON_POT_DEFAULTS)
    if (not isinstance(data, dict) or set(data) != expected or type(data.get('schema')) is not int
            or data['schema'] != 5 or not isinstance(data['pots'], list) or not 1 <= len(data['pots']) <= 2):
        raise ValueError('v5 저장 항목 오류')
    migrated = deepcopy(data)
    for pot in migrated['pots']:
        if (not isinstance(pot, dict) or set(pot) != old_pot_fields
                or pot['ruleset_id'] not in (None, 'v0.4', 'legacy-v3')
                or pot['care_profile'] == 'repeat'):
            raise ValueError('v5 화분 항목 오류')
        pot.update(TYCOON_POT_DEFAULTS)
    migrated.update(schema=6, fertilizer=0, reward_wait=0.0, last_reward_id=None)
    _v6_to_v7(migrated)
    return migrated


def _v6_to_v7(data):
    expected = set(Garden(0).to_dict()) - V8_FIELDS - {'owned_skins', 'equipped_skin'}
    if (not isinstance(data, dict) or set(data) != expected
            or type(data.get('schema')) is not int or data['schema'] != 6):
        raise ValueError('v6 저장 항목 오류')
    migrated = deepcopy(data)
    migrated.update(schema=7, owned_skins=['terracotta'], equipped_skin='terracotta')
    _v7_to_v8(migrated)
    return migrated


def _v7_to_v8(data):
    expected = set(Garden(0).to_dict()) - V8_FIELDS
    if not isinstance(data, dict) or set(data) != expected or type(data.get('schema')) is not int or data['schema'] != 7:
        raise ValueError('v7 저장 항목 오류')
    if type(data['fertilizer']) is not int or not 0 <= data['fertilizer'] <= 10:
        raise ValueError('v7 비료 재고')
    if not _number(data['reward_wait']) or not 0 <= data['reward_wait'] <= 1800:
        raise ValueError('v7 비료 대기')
    if data['reward_wait'] > 0 and data['last_reward_id'] is None:
        raise ValueError('v7 비료 지급 기록 없음')
    migrated = deepcopy(data)
    defaults = Garden(0).to_dict()
    migrated.update({key: defaults[key] for key in V8_FIELDS})
    migrated.update(schema=8, fertilizer=min(5, data['fertilizer']),
                    fertilizer_reserve=max(0, data['fertilizer'] - 5),
                    reward_wait=max(0.0, data['reward_wait'] - 1620))
    _v8_to_v9(migrated)
    return migrated


def _v8_to_v9(data):
    migrated = {**deepcopy(data), 'schema': 9}
    state = Garden.from_dict(migrated)
    if not set(state.desktop_flowers) <= {item['id'] for item in state.collection}:
        raise ValueError('v8 바탕화면 꽃 식별')
    return migrated


def migrate(data):
    """Return current-schema data without mutating the source document."""
    if not isinstance(data, dict):
        return data
    migrated = deepcopy(data)
    schema = migrated.get('schema')
    if type(schema) is not int:
        return migrated
    if schema == 1:
        legacy_seeds = migrated.pop('seeds', 0)
        migrated.update(
            schema=2,
            species='daisy' if migrated.get('planted') else None,
            mist_progress=0,
            seeds={key: legacy_seeds if key == 'daisy' else 0 for key in LEGACY_SPECIES},
        )
    if migrated.get('schema') == 2:
        migrated = _v2_to_v3(migrated)
    if migrated.get('schema') == 3:
        migrated = _v3_to_v4(migrated)
    if migrated.get('schema') == 4:
        migrated = _v4_to_v5(migrated)
    if migrated.get('schema') == 5:
        migrated = _v5_to_v6(migrated)
    if migrated.get('schema') == 6:
        migrated = _v6_to_v7(migrated)
    if migrated.get('schema') == 7:
        migrated = _v7_to_v8(migrated)
    if migrated.get('schema') == 8:
        migrated = _v8_to_v9(migrated)
    return migrated


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.backup = self.path.with_suffix('.json.bak')
        self.cloud_backup = self.path.with_suffix('.json.pre-cloud.bak')
        self.migration_backup = self.path.with_suffix('.json.v3-migration.bak')
        self.blocked = False
        self.notice = ''
        self._migration_source = None

    def load(self, now):
        if not self.path.exists() and not self.backup.exists():
            return Garden(now)
        for path in (self.path, self.backup):
            try:
                raw = path.read_text(encoding='utf-8')
                data = json.loads(raw)
                if (
                    isinstance(data, dict)
                    and _number(data.get('schema'))
                    and data['schema'] > Garden.CURRENT_SCHEMA
                ):
                    self.blocked = True
                    raise SaveError('새 버전의 저장 파일입니다. 원본을 보존하고 앱을 업데이트하세요.')
                migrated = migrate(data)
                state = Garden.from_dict(migrated)
                if isinstance(data, dict) and data.get('schema') in (1, 2, 3, 4, 5, 6, 7, 8):
                    self._migration_source = raw
                    if data['schema'] in (5, 6, 7, 8):
                        self.migration_backup = self.path.with_suffix(f'.json.v{data["schema"]}-migration.bak')
                    self.notice = '기존 저장을 v9로 이전했습니다. 꽃·재화·꾸미기·바탕화면 배치를 보존합니다.'
                elif path == self.backup:
                    self.notice = '직전 정상 백업에서 복구했습니다.'
                state.advance(now)
                return state
            except SaveError:
                raise
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        self.blocked = True
        raise SaveError('저장 파일과 백업을 읽을 수 없습니다. 원본을 보존했습니다.')

    def save(self, state):
        if self.blocked:
            raise SaveError('저장 파일 보호 중')
        Garden.from_dict(state.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self._migration_source is not None and not self.migration_backup.exists():
                self._atomic(self.migration_backup, self._migration_source)
            if self.path.exists():
                try:
                    old = self.path.read_text(encoding='utf-8')
                    Garden.from_dict(migrate(json.loads(old)))
                except (ValueError, TypeError, json.JSONDecodeError):
                    pass
                else:
                    self._atomic(self.backup, old)
            self._atomic(self.path, json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            self._migration_source = None
        except OSError as exc:
            raise SaveError(str(exc)) from exc

    def replace_from_cloud(self, data, now):
        """Validate a cloud save and atomically install it, retaining the local save."""
        if self.blocked:
            raise SaveError('저장 파일 보호 중')
        try:
            if (isinstance(data, dict) and type(data.get('schema')) is int
                    and data['schema'] > Garden.CURRENT_SCHEMA):
                raise SaveError('클라우드 저장이 더 새로운 버전입니다. 앱을 업데이트하세요.')
            state = Garden.from_dict(migrate(data))
            state.advance(now)
            current = self.path.read_text(encoding='utf-8') if self.path.exists() else None
            if current is not None:
                self._atomic(self.cloud_backup, current)
            self._atomic(self.path, json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return state
        except SaveError:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SaveError('클라우드 저장을 적용할 수 없습니다.') from exc

    @staticmethod
    def _atomic(path, text):
        tmp = path.with_suffix(path.suffix + '.tmp')
        with tmp.open('w', encoding='utf-8') as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
