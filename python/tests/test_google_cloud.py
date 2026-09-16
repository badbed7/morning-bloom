import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from morning_bloom.google_cloud import CloudError, GoogleDriveSync, configured_client_id, oauth_url
from morning_bloom.model import Garden
from morning_bloom.storage import SaveError, Store


CLIENT_ID = '123-example.apps.googleusercontent.com'


class GoogleCloudSave(unittest.TestCase):
    def test_packaged_client_id_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict('os.environ', {'MORNING_BLOOM_GOOGLE_CLIENT_ID': ''}), \
                patch('sys.frozen', True, create=True), patch('sys._MEIPASS', tmp, create=True):
            Path(tmp, 'google-oauth-client-id.txt').write_text(CLIENT_ID, encoding='utf-8')
            self.assertEqual(configured_client_id(), CLIENT_ID)

    def test_oauth_url_uses_pkce_without_client_secret(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(
            oauth_url(CLIENT_ID, 'http://127.0.0.1:4567/oauth2callback', 'state', 'verifier')
        ).query)
        self.assertEqual(query['client_id'], [CLIENT_ID])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['state'], ['state'])
        self.assertIn('https://www.googleapis.com/auth/drive.appdata', query['scope'][0])
        self.assertNotIn('client_secret', query)

    def test_upload_creates_private_app_data_file(self):
        sync = GoogleDriveSync(CLIENT_ID, {'refresh_token': 'refresh'}, clock=lambda: 200)
        with patch.object(sync, '_file_id', return_value=None), \
                patch.object(sync, '_token', return_value='access'), \
                patch('morning_bloom.google_cloud._json_request') as request:
            request.side_effect = [{'id': 'file-id'}, {}]
            saved_at = sync.upload_save({'schema': Garden.CURRENT_SCHEMA})
        self.assertEqual(saved_at, 200)
        self.assertEqual(request.call_args_list[0].args[3]['parents'], ['appDataFolder'])
        uploaded = request.call_args_list[1].args[3]
        self.assertEqual(uploaded['save']['schema'], Garden.CURRENT_SCHEMA)
        self.assertEqual(uploaded['saved_at'], 200)

    def test_download_rejects_invalid_envelope(self):
        sync = GoogleDriveSync(CLIENT_ID, {'refresh_token': 'refresh'})
        with patch.object(sync, '_file_id', return_value='file-id'), \
                patch.object(sync, '_token', return_value='access'), \
                patch('morning_bloom.google_cloud._request', return_value=b'{}'):
            with self.assertRaises(CloudError):
                sync.download_save()

    def test_cloud_restore_keeps_local_backup_and_rejects_future_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'garden.json')
            local = Garden(100)
            local.coins = 321
            store.save(local)
            cloud = Garden(100)
            cloud.coins = 77
            restored = store.replace_from_cloud(cloud.to_dict(), 120)
            self.assertEqual(restored.coins, 77)
            self.assertEqual(json.loads(store.cloud_backup.read_text(encoding='utf-8'))['coins'], 321)
            current = store.path.read_text(encoding='utf-8')
            future = cloud.to_dict()
            future['schema'] = Garden.CURRENT_SCHEMA + 1
            with self.assertRaises(SaveError):
                store.replace_from_cloud(future, 130)
            self.assertEqual(store.path.read_text(encoding='utf-8'), current)


if __name__ == '__main__':
    unittest.main()
