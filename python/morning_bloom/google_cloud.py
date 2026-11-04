"""Google desktop OAuth and private Drive app-data save sync."""
import base64
import ctypes
import hashlib
import json
import math
import logging
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from .tls import create_context

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
DRIVE_UPLOAD_URL = 'https://www.googleapis.com/upload/drive/v3/files'
SCOPES = ('openid', 'email', 'profile', 'https://www.googleapis.com/auth/drive.appdata')
LEGACY_SAVE_NAME = 'morning-bloom-save-v1.json'
SAVE_NAME = 'morning-bloom-save-v2.json'
CREDENTIAL_TARGET = 'MorningBloom/GoogleDrive'
_UNSET = object()


class CloudError(Exception):
    """Safe, structured failure metadata. Never expose request bodies or tokens."""
    def __init__(self, message, *, stage='unknown', status=None, code='', reason='', location=''):
        self.stage, self.status = stage, status
        self.code, self.reason, self.location = code, reason, location
        self.auth_required = code in ('invalid_grant', 'client_changed', 'login_required')
        self.retryable = status in (408, 429, 500, 502, 503, 504) or code in ('network_error', 'conflict') or reason in ('rateLimitExceeded', 'userRateLimitExceeded')
        self.guidance = ('Google 계정을 다시 연결하세요.' if self.auth_required else
                         '앱의 Google OAuth 설정을 확인하세요.' if code == 'invalid_client' else
                         'Google Drive API 활성화와 권한 설정을 확인하세요.' if status == 403 and not self.retryable else
                         '잠시 후 다시 백업하세요.' if self.retryable else
                         '오류 단계와 코드를 확인하세요. 로컬 정원은 보존됩니다.')
        metadata = ' · '.join(str(v) for v in (stage if stage != 'unknown' else '', status, code, reason, location) if v)
        super().__init__(message + (' [' + metadata + ']' if metadata else ''))


def _safe_field(value):
    # Codes and parameter names only; arbitrary server text may contain secrets.
    import re
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,79}', value) else ''


def _stage(url, method):
    if url == TOKEN_URL:
        return 'token'
    if url.startswith(DRIVE_UPLOAD_URL):
        return 'upload'
    if url.startswith(DRIVE_FILES_URL):
        return 'create' if method == 'POST' else 'download' if 'alt=media' in url else 'list'
    if url == USERINFO_URL:
        return 'profile'
    return 'oauth'



def configured_client_id():
    value = os.environ.get('MORNING_BLOOM_GOOGLE_CLIENT_ID', '').strip()
    if value:
        return value
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    path = root / 'google-oauth-client-id.txt'
    if path.is_file():
        return path.read_text(encoding='utf-8').strip()
    return ''


def configured_client_secret():
    value = os.environ.get('MORNING_BLOOM_GOOGLE_CLIENT_SECRET', '').strip()
    if value:
        return value
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    path = root / 'google-oauth-client-secret.txt'
    if path.is_file():
        return path.read_text(encoding='utf-8').strip()
    return ''


def _client_fields(client_id, client_secret):
    fields = {'client_id': client_id}
    if client_secret:
        fields['client_secret'] = client_secret
    return fields


def _request(url, method='GET', token=None, body=None, content_type=None, timeout=20):
    headers = {'Accept': 'application/json', 'User-Agent': 'MorningBloom/1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if content_type:
        headers['Content-Type'] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    stage = _stage(url, method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=create_context()) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            code = reason = location = ''
            try:
                payload = json.loads(exc.read().decode('utf-8'))
                detail = payload.get('error', {})
                if isinstance(detail, dict):
                    errors = detail.get('errors', [])
                    info = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
                    code = _safe_field(detail.get('status'))
                    reason, location = _safe_field(info.get('reason')), _safe_field(info.get('location'))
                else:
                    code = _safe_field(detail)
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
                pass
            failure = CloudError('Google 요청 실패', stage=stage, status=exc.code,
                                 code=code, reason=reason, location=location)
            # Never retry file creation automatically; a lost response may already have created it.
            if failure.retryable and method != 'POST' and attempt < 2:
                time.sleep(.2 * (attempt + 1))
                continue
            logging.getLogger(__name__).warning('cloud stage=%s status=%s code=%s reason=%s location=%s',
                stage, exc.code, code, reason, location)
            raise failure from exc
        except (urllib.error.URLError, OSError) as exc:
            raise CloudError('Google 서비스에 연결할 수 없습니다.', stage=stage, code='network_error') from exc


def _json_request(url, method='GET', token=None, data=None):
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
    raw = _request(url, method, token, body, 'application/json' if body is not None else None)
    try:
        result = json.loads(raw.decode('utf-8')) if raw else {}
        if not isinstance(result, dict):
            raise ValueError('Expected a JSON object')
        return result
    except (UnicodeDecodeError, ValueError) as exc:
        raise CloudError('Google 응답을 읽을 수 없습니다.') from exc


def _form_request(url, values):
    body = urllib.parse.urlencode(values).encode('ascii')
    raw = _request(url, 'POST', body=body, content_type='application/x-www-form-urlencoded')
    try:
        result = json.loads(raw.decode('utf-8')) if raw else {}
        if not isinstance(result, dict):
            raise ValueError('Expected a JSON object')
        return result
    except (UnicodeDecodeError, ValueError) as exc:
        raise CloudError('Google 인증 응답을 읽을 수 없습니다.') from exc


def oauth_url(client_id, redirect_uri, state, verifier):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    return AUTH_URL + '?' + urllib.parse.urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'state': state,
    })


def _wait_for_callback(server, result, timeout):
    deadline = time.monotonic() + timeout
    while 'state' not in result and time.monotonic() < deadline:
        server.timeout = max(0, deadline - time.monotonic())
        server.handle_request()


def authorize(client_id, browser_open=webbrowser.open, timeout=180, client_secret=''):
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != '/oauth2callback':
                self.send_response(204)
                self.end_headers()
                return
            query = urllib.parse.parse_qs(parsed.query)
            result.update({key: values[0] for key, values in query.items() if values})
            page = '<meta charset="utf-8"><title>Morning Bloom</title><p>Morning Bloom으로 돌아가세요.</p>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(page.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(page.encode('utf-8'))

        def log_message(self, *_):
            pass

    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    server = HTTPServer(('127.0.0.1', 0), Callback)
    redirect_uri = f'http://127.0.0.1:{server.server_port}/oauth2callback'
    try:
        try:
            opened = browser_open(oauth_url(client_id, redirect_uri, state, verifier))
        except (OSError, webbrowser.Error) as exc:
            raise CloudError('로그인 브라우저를 열지 못했습니다.', stage='browser') from exc
        if opened is False:
            raise CloudError('로그인 브라우저를 열지 못했습니다.', stage='browser')
        _wait_for_callback(server, result, timeout)
    finally:
        server.server_close()
    if not result:
        raise CloudError('Google 로그인 시간이 만료되었습니다.', stage='callback')
    if result.get('state') != state:
        raise CloudError('Google 로그인 응답을 확인할 수 없습니다.')
    if result.get('error'):
        raise CloudError('Google 로그인이 취소되었습니다.')
    code = result.get('code')
    if not code:
        raise CloudError('Google 로그인 시간이 만료되었습니다.')
    tokens = _form_request(TOKEN_URL, {
        **_client_fields(client_id, client_secret), 'code': code, 'code_verifier': verifier,
        'grant_type': 'authorization_code', 'redirect_uri': redirect_uri,
    })
    if not tokens.get('access_token') or not tokens.get('refresh_token'):
        raise CloudError('Google 장기 로그인 권한을 받지 못했습니다.')
    profile = _json_request(USERINFO_URL, token=tokens['access_token'])
    tokens['email'] = profile.get('email', '')
    tokens['expires_at'] = time.time() + int(tokens.get('expires_in', 3600))
    return tokens


class _Credential(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), ('Type', wintypes.DWORD), ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR), ('LastWritten', wintypes.FILETIME),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(wintypes.BYTE)), ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR),
    ]


def _credential_api():
    if sys.platform != 'win32':
        raise CloudError('Google 연결은 Windows에서만 지원합니다.')
    api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    return api


def save_credentials(data):
    blob = json.dumps(data, ensure_ascii=False).encode('utf-8')
    if len(blob) > 2560:
        raise CloudError('Google 인증 정보가 너무 큽니다.')
    api = _credential_api()
    buffer = ctypes.create_string_buffer(blob)
    credential = _Credential(
        0, 1, CREDENTIAL_TARGET, 'Morning Bloom Google Drive', wintypes.FILETIME(),
        len(blob), ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE)), 2, 0, None,
        None, data.get('email') or 'Google',
    )
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise CloudError('Windows 자격 증명 관리자에 로그인 정보를 저장하지 못했습니다.')


def load_credentials():
    if sys.platform != 'win32':
        return {}
    api = _credential_api()
    pointer = ctypes.POINTER(_Credential)()
    if not api.CredReadW(CREDENTIAL_TARGET, 1, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == 1168:
            return {}
        raise CloudError('Windows 자격 증명 관리자에서 로그인 정보를 읽지 못했습니다.')
    try:
        raw = ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize)
        data = json.loads(raw.decode('utf-8'))
        return data if isinstance(data, dict) else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    finally:
        api.CredFree(pointer)


def delete_credentials():
    if sys.platform != 'win32':
        return
    api = _credential_api()
    if not api.CredDeleteW(CREDENTIAL_TARGET, 1, 0) and ctypes.get_last_error() != 1168:
        raise CloudError('Windows 자격 증명 관리자에서 연결 정보를 지우지 못했습니다.')


class GoogleDriveSync:
    def __init__(self, client_id=None, credentials=_UNSET, clock=time.time, client_secret=None):
        self.client_id = (client_id if client_id is not None else configured_client_id()).strip()
        self.client_secret = (client_secret if client_secret is not None else configured_client_secret()).strip()
        self.clock = clock
        try:
            if credentials is _UNSET:
                self.credentials = load_credentials() if self.client_id else {}
            else:
                self.credentials = dict(credentials or {})
        except CloudError:
            self.credentials = {}
        self._access_token = ''
        self._expires_at = 0.0
        self._observed_refs = None
        self.reauth_required = bool(self.credentials.get('reauth_required')) or bool(self.credentials.get('client_id') and self.credentials['client_id'] != self.client_id)
        self.auto_retry_allowed = not self.reauth_required
        self.last_error = '저장된 인증을 사용할 수 없습니다. Google 계정을 다시 연결하세요.' if self.reauth_required else ''

    @property
    def configured(self):
        return self.client_id.endswith('.apps.googleusercontent.com') and bool(self.client_secret)

    @property
    def connected(self):
        return self.configured and bool(self.credentials.get('refresh_token')) and not self.reauth_required

    @property
    def email(self):
        return self.credentials.get('email', '')

    def connect(self):
        if not self.configured:
            raise CloudError('Google OAuth 클라이언트 설정이 필요합니다.')
        tokens = authorize(self.client_id, client_secret=self.client_secret)
        saved = {'refresh_token': tokens['refresh_token'], 'email': tokens.get('email', ''), 'client_id': self.client_id}
        save_credentials(saved)
        self.credentials = saved
        self._observed_refs = None
        self.reauth_required = False
        self.auto_retry_allowed = True
        self.last_error = ''
        self._access_token = tokens['access_token']
        self._expires_at = tokens['expires_at']
        return self.email

    def disconnect(self):
        token = self.credentials.get('refresh_token')
        try:
            if token:
                _form_request(REVOKE_URL, {'token': token})
        except CloudError:
            pass
        delete_credentials()
        self.credentials = {}
        self.reauth_required = False
        self.auto_retry_allowed = True
        self.last_error = ''
        self._access_token = ''
        self._expires_at = 0
        self._observed_refs = None

    def _record_error(self, error):
        self.last_error = str(error) + ' ' + error.guidance
        self.auto_retry_allowed = error.retryable
        if error.auth_required:
            self.reauth_required = True
            self._access_token = ''
            self.credentials['reauth_required'] = True
            try:
                save_credentials(self.credentials)
            except CloudError:
                pass

    def _drive_call(self, call):
        try:
            return call()
        except CloudError as error:
            if error.status == 401:
                self._access_token = ''
                self._expires_at = 0
                try:
                    result = call()  # Refresh access token once, then retry once.
                    self.auto_retry_allowed = True
                    self.last_error = ''
                    return result
                except CloudError as retry_error:
                    error = retry_error
            self._record_error(error)
            raise error

    def _token(self):
        if self.reauth_required:
            raise CloudError('Google 계정 재연결이 필요합니다.', stage='token', code='login_required')
        if self._access_token and self.clock() < self._expires_at - 60:
            return self._access_token
        refresh = self.credentials.get('refresh_token')
        if not refresh:
            raise CloudError('Google 계정 연결이 필요합니다.')
        try:
            result = _form_request(TOKEN_URL, {
                **_client_fields(self.client_id, self.client_secret), 'refresh_token': refresh,
                'grant_type': 'refresh_token',
            })
        except CloudError as error:
            self._record_error(error)
            raise
        if self.credentials.get('client_id') != self.client_id:
            self.credentials['client_id'] = self.client_id
            try:
                save_credentials(self.credentials)
            except CloudError:
                pass
        self._access_token = result.get('access_token', '')
        self._expires_at = self.clock() + int(result.get('expires_in', 3600))
        if not self._access_token:
            raise CloudError('Google 로그인을 갱신하지 못했습니다.', stage='token', code='login_required')
        return self._access_token

    def _files(self):
        files, page_token, seen = [], None, set()
        while True:
            query = {
                'spaces': 'appDataFolder',
                'q': f"(name='{SAVE_NAME}' or name='{LEGACY_SAVE_NAME}') and trashed=false",
                'orderBy': 'modifiedTime desc', 'pageSize': 1000,
                'fields': 'nextPageToken,files(id,version,size,appProperties)',
            }
            if page_token:
                query['pageToken'] = page_token
            result = self._drive_call(lambda: _json_request(
                DRIVE_FILES_URL + '?' + urllib.parse.urlencode(query), token=self._token()))
            page = result.get('files', [])
            if not isinstance(page, list) or any(not isinstance(f, dict) or not isinstance(f.get('id'), str) or not f.get('id')
                    or not isinstance(f.get('appProperties', {}), dict)
                    or any(not isinstance(k, str) or not isinstance(v, str)
                           for k, v in f.get('appProperties', {}).items()) for f in page):
                raise CloudError('클라우드 저장 목록을 확인할 수 없습니다.')
            # Old releases could create an empty file before a failed PATCH.
            # Ignore only positively identified empty legacy files, never corrupt saves.
            files.extend(f for f in page if not (str(f.get('size')) == '0' and not f.get('appProperties', {}).get('bloom_rev')))
            page_token = result.get('nextPageToken')
            if not page_token:
                return files
            if page_token in seen:
                raise CloudError('클라우드 저장 목록이 반복됩니다.')
            seen.add(page_token)

    @staticmethod
    def _revision(file):
        # Legacy clients can still edit their v1 file. Treat each version as a new
        # head, while keeping v2 journal names outside the old client's query.
        return file.get('appProperties', {}).get('bloom_rev') or f"{file['id']}:{file.get('version', '')}"

    @staticmethod
    def _heads(files):
        superseded = {v for f in files for k, v in f.get('appProperties', {}).items() if k.startswith('bloom_p')}
        heads = [f for f in files if GoogleDriveSync._revision(f) not in superseded]
        if files and not heads:
            raise CloudError('클라우드 백업 연결이 손상되었습니다. 기존 저장을 보존했습니다.')
        return heads

    @staticmethod
    def _refs(files):
        return tuple(sorted((f['id'], str(f.get('version', ''))) for f in files))

    def _file_id(self):
        files = self._heads(self._files())
        return files[0]['id'] if files else None

    def _read_save(self, file):
        file_id = urllib.parse.quote(file['id'], safe='')
        raw = self._drive_call(lambda: _request(f'{DRIVE_FILES_URL}/{file_id}?alt=media', token=self._token()))
        try:
            envelope = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CloudError('클라우드 저장 파일이 손상되었습니다.') from exc
        fields = {'schema', 'saved_at', 'save'}
        if isinstance(envelope, dict) and envelope.get('schema') == 2:
            fields |= {'revision', 'parents'}
        if (not isinstance(envelope, dict) or set(envelope) != fields
                or type(envelope['schema']) is not int or envelope['schema'] not in (1, 2)
                or type(envelope['saved_at']) not in (int, float) or not math.isfinite(envelope['saved_at'])
                or not isinstance(envelope['save'], dict)):
            raise CloudError('지원하지 않는 클라우드 저장 형식입니다.')
        if envelope['schema'] == 2:
            if (envelope['revision'] != file.get('appProperties', {}).get('bloom_rev')
                    or not isinstance(envelope['parents'], list)
                    or any(not isinstance(p, str) for p in envelope['parents'])
                    or set(envelope['parents']) != {v for k, v in file.get('appProperties', {}).items() if k.startswith('bloom_p')}):
                raise CloudError('클라우드 저장 버전을 확인할 수 없습니다.')
        from .model import Garden
        from .storage import migrate
        try:
            # Future or damaged heads must block writing, including manual backup.
            Garden.from_dict(migrate(envelope['save']))
        except (ValueError, TypeError, KeyError) as exc:
            raise CloudError('클라우드 정원을 읽을 수 없습니다. 새 버전 여부를 확인하세요.', code='invalid_save') from exc
        return envelope

    def download_save(self):
        files = self._heads(self._files())
        if len(files) > 32:
            raise CloudError('클라우드 충돌 백업이 너무 많습니다. 로컬 정원을 보존했습니다.')
        envelopes = [self._read_save(file) for file in files]
        self._observed_refs = self._refs(files)
        self.auto_retry_allowed = True
        self.last_error = ''
        if not envelopes:
            return None
        envelope = envelopes[0]
        if len(envelopes) > 1:
            envelope = {**envelope, 'alternatives': envelopes[1:]}
        return envelope

    def upload_save(self, save):
        from .model import Garden
        try:
            Garden.from_dict(save)
        except (ValueError, TypeError) as exc:
            raise CloudError('저장 데이터를 업로드할 수 없습니다.') from exc
        if self._observed_refs is None:
            self.download_save()
        heads = self._heads(self._files())
        if self._refs(heads) != self._observed_refs:
            raise CloudError('다른 PC의 백업이 변경되었습니다. 다시 확인하세요.', code='conflict')
        parents = [self._revision(f) for f in heads]
        revision = secrets.token_hex(16)
        envelope = {'schema': 2, 'saved_at': self.clock(), 'save': save,
                    'revision': revision, 'parents': parents}
        properties = {'bloom_rev': revision, **{f'bloom_p{i}': p for i, p in enumerate(parents)}}
        metadata = {'name': SAVE_NAME, 'parents': ['appDataFolder'], 'appProperties': properties}
        boundary = 'bloom_' + secrets.token_hex(16)
        body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()
                + json.dumps(metadata).encode() +
                f'\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n'.encode()
                + json.dumps(envelope, ensure_ascii=False).encode('utf-8') +
                f'\r\n--{boundary}--\r\n'.encode())
        # Append a complete snapshot in one multipart create. Never overwrite/delete
        # another device's revision. Concurrent children remain separate conflict heads.
        raw = self._drive_call(lambda: _request(
            DRIVE_UPLOAD_URL + '?uploadType=multipart&fields=id', 'POST', self._token(), body,
            f'multipart/related; boundary={boundary}'))
        try:
            created = json.loads(raw.decode('utf-8'))
            if not isinstance(created.get('id'), str) or not created['id']:
                raise ValueError('missing id')
        except (ValueError, AttributeError, UnicodeDecodeError) as exc:
            raise CloudError('백업 응답을 확인하지 못했습니다. 다음 주기에 다시 확인합니다.', code='network_error') from exc
        self._observed_refs = ((created['id'], '1'),)
        self.auto_retry_allowed = True
        self.last_error = ''
        return envelope['saved_at']
