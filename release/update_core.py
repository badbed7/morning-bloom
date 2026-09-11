"""Versioned installs. HTTPS release origin and SHA-256 integrity, no embedded credentials."""
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE = 512 * 1024 * 1024
MAX_UNPACKED = 1536 * 1024 * 1024
VERSION = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')

class UpdateError(Exception): pass

def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise UpdateError('Invalid release version')
    return tuple(map(int, value.split('.')))

def manifest(data, repository):
    if not isinstance(data, dict) or data.get('protocol') != 1:
        raise UpdateError('This update requires a newer launcher')
    version(data.get('version'))
    digest = data.get('sha256')
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise UpdateError('Invalid digest')
    if type(data.get('size')) is not int or not 0 < data['size'] <= MAX_ARCHIVE:
        raise UpdateError('Invalid download size')
    expected = f"https://github.com/{repository}/releases/download/v{data['version']}/MorningBloom-game.zip"
    if data.get('url') != expected:
        raise UpdateError('Unexpected update origin')
    return data

def read_latest(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise UpdateError('Invalid repository')
    url = f'https://github.com/{repository}/releases/latest/download/update.json'
    request = urllib.request.Request(url, headers={'User-Agent': 'MorningBloomLauncher/1'})
    with urllib.request.urlopen(request, timeout=5) as response:
        if not response.url.startswith('https://'):
            raise UpdateError('HTTPS required')
        raw = response.read(65537)
    if len(raw) > 65536: raise UpdateError('Manifest too large')
    return manifest(json.loads(raw), repository)

def verify(path, data):
    if path.stat().st_size != data['size']: raise UpdateError('Download size mismatch')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''): digest.update(chunk)
    if digest.hexdigest() != data['sha256']: raise UpdateError('Download integrity check failed')

def download(data, path, report=lambda _: None):
    request = urllib.request.Request(data['url'], headers={'User-Agent': 'MorningBloomLauncher/1'})
    deadline, total = time.monotonic() + 600, 0
    try:
        with urllib.request.urlopen(request, timeout=15) as response, path.open('wb') as target:
            if not response.url.startswith('https://'): raise UpdateError('HTTPS required')
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > data['size'] or time.monotonic() > deadline:
                    raise UpdateError('Download exceeded limits')
                target.write(chunk)
                report(f'Downloading update... {total * 100 // data["size"]}%')
        verify(path, data)
    except Exception:
        path.unlink(missing_ok=True)
        raise

def extract(archive, target):
    """Reject traversal, symlinks, Windows aliases/ADS, duplicates and zip bombs."""
    seen, total = set(), 0
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 20000: raise UpdateError('Too many archive entries')
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith('/') or '\\' in name or ':' in name
                    or any(p in ('.', '..') or p.rstrip(' .') != p for p in parts)
                    or any(p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in parts)):
                raise UpdateError('Unsafe archive path')
            key = '/'.join(parts).casefold()
            if key in seen: raise UpdateError('Duplicate archive entry')
            seen.add(key)
            if stat.S_ISLNK(item.external_attr >> 16): raise UpdateError('Archive symlink')
            total += item.file_size
            if total > MAX_UNPACKED: raise UpdateError('Archive too large')
        source.extractall(target)
    if not (target / 'MorningBloomGame.exe').is_file():
        raise UpdateError('Missing game executable')

def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as target:
        json.dump(data, target)
        target.flush()
        os.fsync(target.fileno())
    os.replace(tmp, path)

class Installer:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.versions = self.root / 'versions'
        self.versions.mkdir(exist_ok=True)
        self.pointer = self.root / 'current.json'

    def current(self):
        try:
            data = json.loads(self.pointer.read_text())
            version(data['version'])
            if not re.fullmatch('[a-f0-9]{64}', data['sha256']): return None
            if self.executable(data).is_file(): return data
        except (OSError, ValueError, KeyError, TypeError, UpdateError): pass
        return None

    def folder(self, data): return self.versions / (data['version'] + '-' + data['sha256'])
    def executable(self, data): return self.folder(data) / 'MorningBloomGame.exe'

    def install(self, archive, data, health_check):
        verify(Path(archive), data)
        destination = self.folder(data)
        previous = self.current()
        if previous and version(data['version']) < version(previous['version']):
            raise UpdateError('Downgrade refused')
        with tempfile.TemporaryDirectory(prefix='staging-', dir=self.root) as temp:
            stage = Path(temp) / 'game'
            stage.mkdir()
            extract(archive, stage)
            if not health_check(stage / 'MorningBloomGame.exe'):
                raise UpdateError('New game failed startup check')
            if destination.exists():
                if not health_check(destination / 'MorningBloomGame.exe'):
                    raise UpdateError('Existing installation is damaged')
            else:
                os.replace(stage, destination)
        installed = {'version': data['version'], 'sha256': data['sha256']}
        if previous and previous != installed:
            atomic_json(self.root / 'previous.json', previous)
        atomic_json(self.pointer, installed)
        return installed
