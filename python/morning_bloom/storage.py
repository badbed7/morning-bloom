"""Validated v14 persistence; v1-v13 migrate through frozen definitions."""
import json
import os
from copy import deepcopy
from pathlib import Path
from .model import Garden, _number
from .save_v13 import migrate as migrate_legacy

class SaveError(Exception):
    pass

def migrate(data):
    if not isinstance(data, dict) or type(data.get('schema')) is not int:
        return deepcopy(data)
    result = migrate_legacy(data) if data['schema'] < 13 else deepcopy(data)
    return Garden.upgrade_v13(result) if result.get('schema') == 13 else result

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
                if isinstance(data, dict) and data.get('schema') in range(1, Garden.CURRENT_SCHEMA):
                    self._migration_source = raw
                    if data['schema'] >= 5:
                        self.migration_backup = self.path.with_suffix(f'.json.v{data["schema"]}-migration.bak')
                    self.notice = f'기존 저장을 v{Garden.CURRENT_SCHEMA}으로 이전했습니다. 꽃·재화·꾸미기·바탕화면 배치를 보존합니다.'
                elif path == self.backup:
                    self.notice = '직전 정상 백업에서 복구했습니다.'
                if state.progression['board']['prepared'] is not None:
                    from .board_model import transact
                    transact(state,self)
                state.advance(now,context='offline')
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
            if state.progression['board']['prepared'] is not None:
                from .board_model import commit
                commit(state)
            state.advance(now,context='offline')
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
