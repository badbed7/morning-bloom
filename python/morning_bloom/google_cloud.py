"""Google desktop OAuth and private Drive app-data save sync."""
import base64
import ctypes
import hashlib
import json
import math
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

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
DRIVE_UPLOAD_URL = 'https://www.googleapis.com/upload/drive/v3/files'
SCOPES = ('openid', 'email', 'profile', 'https://www.googleapis.com/auth/drive.appdata')
SAVE_NAME = 'morning-bloom-save-v1.json'
CREDENTIAL_TARGET = 'MorningBloom/GoogleDrive'
_UNSET = object()


class CloudError(Exception):
    pass


def configured_client_id():
    value = os.environ.get('MORNING_BLOOM_GOOGLE_CLIENT_ID', '').strip()
    if value:
        return value
    if getattr(sys, 'frozen', False):
        path = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'google-oauth-client-id.txt'
        if path.is_file():
            return path.read_text(encoding='utf-8').strip()
    return ''


def _request(url, method='GET', token=None, body=None, content_type=None, timeout=20):
    headers = {'Accept': 'application/json', 'User-Agent': 'MorningBloom/1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if content_type:
        headers['Content-Type'] = content_type
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode('utf-8')).get('error', {})
            message = detail.get('message') if isinstance(detail, dict) else detail
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            message = None
        raise CloudError(message or f'Google 요청 실패 ({exc.code})') from exc
    except (urllib.error.URLError, OSError) as exc:
        raise CloudError('Google 서비스에 연결할 수 없습니다.') from exc


def _json_request(url, method='GET', token=None, data=None):
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
    raw = _request(url, method, token, body, 'application/json' if body is not None else None)
    try:
        return json.loads(raw.decode('utf-8')) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudError('Google 응답을 읽을 수 없습니다.') from exc


def _form_request(url, values):
    body = urllib.parse.urlencode(values).encode('ascii')
    raw = _request(url, 'POST', body=body, content_type='application/x-www-form-urlencoded')
    try:
        return json.loads(raw.decode('utf-8')) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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


def authorize(client_id, browser_open=webbrowser.open, timeout=180):
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
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
    server.timeout = timeout
    redirect_uri = f'http://127.0.0.1:{server.server_port}/oauth2callback'
    try:
        browser_open(oauth_url(client_id, redirect_uri, state, verifier))
        server.handle_request()
    finally:
        server.server_close()
    if result.get('state') != state:
        raise CloudError('Google 로그인 응답을 확인할 수 없습니다.')
    if result.get('error'):
        raise CloudError('Google 로그인이 취소되었습니다.')
    code = result.get('code')
    if not code:
        raise CloudError('Google 로그인 시간이 만료되었습니다.')
    tokens = _form_request(TOKEN_URL, {
        'client_id': client_id, 'code': code, 'code_verifier': verifier,
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
    def __init__(self, client_id=None, credentials=_UNSET, clock=time.time):
        self.client_id = (client_id if client_id is not None else configured_client_id()).strip()
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

    @property
    def configured(self):
        return self.client_id.endswith('.apps.googleusercontent.com')

    @property
    def connected(self):
        return self.configured and bool(self.credentials.get('refresh_token'))

    @property
    def email(self):
        return self.credentials.get('email', '')

    def connect(self):
        if not self.configured:
            raise CloudError('Google OAuth Client ID가 설정되지 않았습니다.')
        tokens = authorize(self.client_id)
        saved = {'refresh_token': tokens['refresh_token'], 'email': tokens.get('email', '')}
        save_credentials(saved)
        self.credentials = saved
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
        self._access_token = ''
        self._expires_at = 0

    def _token(self):
        if self._access_token and self.clock() < self._expires_at - 60:
            return self._access_token
        refresh = self.credentials.get('refresh_token')
        if not refresh:
            raise CloudError('Google 계정 연결이 필요합니다.')
        result = _form_request(TOKEN_URL, {
            'client_id': self.client_id, 'refresh_token': refresh,
            'grant_type': 'refresh_token',
        })
        self._access_token = result.get('access_token', '')
        self._expires_at = self.clock() + int(result.get('expires_in', 3600))
        if not self._access_token:
            raise CloudError('Google 로그인을 갱신하지 못했습니다. 다시 연결하세요.')
        return self._access_token

    def _file_id(self):
        query = urllib.parse.urlencode({
            'spaces': 'appDataFolder', 'q': f"name='{SAVE_NAME}'",
            'orderBy': 'modifiedTime desc', 'pageSize': 1, 'fields': 'files(id)',
        })
        result = _json_request(DRIVE_FILES_URL + '?' + query, token=self._token())
        files = result.get('files', [])
        return files[0].get('id') if files else None

    def download_save(self):
        file_id = self._file_id()
        if not file_id:
            return None
        raw = _request(f'{DRIVE_FILES_URL}/{urllib.parse.quote(file_id, safe="")}?alt=media', token=self._token())
        try:
            envelope = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudError('클라우드 저장 파일이 손상되었습니다.') from exc
        if (not isinstance(envelope, dict) or set(envelope) != {'schema', 'saved_at', 'save'}
                or envelope['schema'] != 1 or type(envelope['saved_at']) not in (int, float)
                or not math.isfinite(envelope['saved_at'])
                or not isinstance(envelope['save'], dict)):
            raise CloudError('지원하지 않는 클라우드 저장 형식입니다.')
        return envelope

    def upload_save(self, save):
        if not isinstance(save, dict):
            raise CloudError('저장 데이터를 업로드할 수 없습니다.')
        envelope = {'schema': 1, 'saved_at': self.clock(), 'save': save}
        file_id = self._file_id()
        token = self._token()
        if not file_id:
            created = _json_request(DRIVE_FILES_URL + '?fields=id', 'POST', token, {
                'name': SAVE_NAME, 'parents': ['appDataFolder'],
            })
            file_id = created.get('id')
            if not file_id:
                raise CloudError('Google Drive 저장 파일을 만들지 못했습니다.')
        _json_request(
            f'{DRIVE_UPLOAD_URL}/{urllib.parse.quote(file_id, safe="")}?uploadType=media',
            'PATCH', token, envelope,
        )
        return envelope['saved_at']
