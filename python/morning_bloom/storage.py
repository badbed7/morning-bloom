"""Atomic saves; malformed or future-version files are never overwritten."""
import json
import os
from pathlib import Path
from .model import Garden

class SaveError(Exception): pass

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.backup = self.path.with_suffix('.json.bak')
        self.blocked = False
        self.notice = ''

    def load(self, now):
        if not self.path.exists() and not self.backup.exists(): return Garden(now)
        for path in (self.path, self.backup):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict) and type(data.get('schema')) in (int, float) and data['schema'] > 1:
                    self.blocked = True
                    raise SaveError('새 버전의 저장 파일입니다. 원본을 보존하고 앱을 업데이트하세요.')
                state = Garden.from_dict(data)
                if path == self.backup: self.notice = '직전 정상 백업에서 복구했습니다.'
                return state
            except (OSError, ValueError, TypeError):
                continue
        self.blocked = True
        raise SaveError('저장 파일과 백업을 읽을 수 없습니다. 원본을 보존했습니다.')

    def save(self, state):
        if self.blocked: raise SaveError('저장 파일 보호 중')
        Garden.from_dict(state.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Rotate only a validated primary; never replace a good backup with corruption.
            if self.path.exists():
                try:
                    old = self.path.read_text(encoding='utf-8')
                    Garden.from_dict(json.loads(old))
                except (ValueError, TypeError): pass
                else: self._atomic(self.backup, old)
            self._atomic(self.path, json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
        except OSError as exc: raise SaveError(str(exc)) from exc

    @staticmethod
    def _atomic(path, text):
        tmp = path.with_suffix(path.suffix + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
