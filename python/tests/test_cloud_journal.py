"""Real loopback HTTP exercises complete writes and simultaneous device backups."""
from legacy_fixture import v19_shape
from copy import deepcopy
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
from unittest.mock import patch

from morning_bloom.google_cloud import CloudError, GoogleDriveSync, SAVE_NAME
from morning_bloom.model import Garden


class CloudJournal(unittest.TestCase):
    def setUp(self):
        self.files = []
        self.lock = threading.Lock()
        self.barrier = None
        self.fail_create = False
        self.lose_response = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value):
                body = value if isinstance(value, bytes) else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                with owner.lock:
                    if 'alt=media' in self.path:
                        file_id = self.path.split('?')[0].split('/')[-1]
                        value = next(f['body'] for f in owner.files if f['id'] == file_id)
                    else:
                        value = {'files': [{k: v for k, v in f.items() if k != 'body'}
                                           for f in reversed(owner.files)]}
                self.reply(200, value)

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                message = BytesParser(policy=policy.default).parsebytes(
                    ('Content-Type: ' + self.headers['Content-Type'] + '\r\n\r\n').encode() + body)
                parts = list(message.iter_parts())
                metadata, envelope = [json.loads(p.get_payload(decode=True)) for p in parts]
                assert metadata['parents'] == ['appDataFolder']
                assert metadata['name'] == SAVE_NAME
                Garden.from_dict(envelope['save'])
                if owner.fail_create:
                    self.reply(503, {'error': {'status': 'UNAVAILABLE'}})
                    return
                if owner.barrier:
                    owner.barrier.wait(5)
                with owner.lock:
                    file_id = 'f' + str(len(owner.files) + 1)
                    raw = json.dumps(envelope).encode()
                    owner.files.append(dict(id=file_id, version='1', size=str(len(raw)),
                                            appProperties=metadata['appProperties'], body=raw))
                self.reply(503 if owner.lose_response else 200,
                           {'error': {'status': 'UNAVAILABLE'}} if owner.lose_response else {'id': file_id})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        base = f'http://127.0.0.1:{self.server.server_port}'
        self.files_patch = patch('morning_bloom.google_cloud.DRIVE_FILES_URL', base + '/files')
        self.upload_patch = patch('morning_bloom.google_cloud.DRIVE_UPLOAD_URL', base + '/upload')
        self.files_patch.start()
        self.upload_patch.start()

    def tearDown(self):
        self.files_patch.stop()
        self.upload_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def device(self):
        sync = GoogleDriveSync('test.apps.googleusercontent.com', {'refresh_token': 'dummy'}, client_secret='dummy')
        sync._access_token, sync._expires_at = 'dummy', time.time() + 3600
        return sync

    def test_complete_create_roundtrip_and_failed_initial_upload_retries_without_empty_file(self):
        device = self.device()
        self.fail_create = True
        with self.assertRaises(CloudError):
            device.upload_save(Garden(100).to_dict())
        self.assertEqual(self.files, [])
        self.fail_create = False
        saved = device.upload_save(Garden(100, coins=345).to_dict())
        self.assertEqual(len(self.files), 1)
        envelope = device.download_save()
        self.assertEqual(envelope['saved_at'], saved)
        self.assertEqual(envelope['save']['coins'], 345)
        self.assertEqual(envelope['schema'], 2)

    def test_concurrent_writes_keep_both_revisions_and_resolve_without_deleting_them(self):
        first, second = self.device(), self.device()
        first.upload_save(Garden(100).to_dict())
        first.download_save()
        second.download_save()
        self.barrier = threading.Barrier(2)
        failures = []
        def upload(device, coins):
            try:
                device.upload_save(Garden(100, coins=coins).to_dict())
            except Exception as error:
                failures.append(error)
        workers = [threading.Thread(target=upload, args=(first, 200)),
                   threading.Thread(target=upload, args=(second, 900))]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(8)
            self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.barrier = None
        self.assertEqual(len(self.files), 3)
        envelope = first.download_save()
        self.assertEqual({envelope['save']['coins'], envelope['alternatives'][0]['save']['coins']}, {200, 900})
        retained = deepcopy(self.files)
        first.upload_save(Garden(100, coins=900).to_dict())
        self.assertEqual(first.download_save()['save']['coins'], 900)
        self.assertNotIn('alternatives', first.download_save())
        self.assertEqual(self.files[:3], retained)

    def test_stale_preflight_refuses_upload_without_creating_revision(self):
        first, second = self.device(), self.device()
        first.upload_save(Garden(100).to_dict())
        first.download_save()
        second.download_save()
        second.upload_save(Garden(100, coins=900).to_dict())
        with self.assertRaises(CloudError) as failure:
            first.upload_save(Garden(100, coins=200).to_dict())
        self.assertEqual(failure.exception.code, 'conflict')
        self.assertEqual(len(self.files), 2)

    def test_lost_success_response_is_recoverable_as_complete_snapshot(self):
        device = self.device()
        self.lose_response = True
        with self.assertRaises(CloudError):
            device.upload_save(Garden(100, coins=400).to_dict())
        self.assertEqual(len(self.files), 1)
        self.lose_response = False
        self.assertEqual(device.download_save()['save']['coins'], 400)

    def test_empty_legacy_file_is_ignored_but_corrupt_or_future_save_blocks_writing(self):
        self.files.append(dict(id='empty', size='0', version='1', body=b''))
        device = self.device()
        self.assertIsNone(device.download_save())
        for raw in (b'broken', json.dumps({'schema': 1, 'saved_at': 100, 'save': {'schema': 999}}).encode()):
            self.files[:] = [dict(id='bad', size=str(len(raw)), version='1', body=raw)]
            with self.assertRaises(CloudError):
                self.device().upload_save(Garden(100).to_dict())
            self.assertEqual(len(self.files), 1)

    def test_legacy_save_restores_then_migrates_to_a_new_revision(self):
        old = Garden(100, coins=500).to_dict()
        old.pop('pot_skins')
        old.pop('pot_colors')
        old.pop('flower_pots')
        old['schema'] = 17
        old = v19_shape(old)
        raw = json.dumps({'schema': 1, 'saved_at': 100, 'save': old}).encode()
        self.files.append(dict(id='legacy', size=str(len(raw)), version='1', body=raw))
        device = self.device()
        self.assertEqual(device.download_save()['save']['schema'], 17)
        device.upload_save(Garden(100, coins=501).to_dict())
        self.assertEqual(device.download_save()['save']['coins'], 501)
        self.assertEqual(self.files[0]['body'], raw)
        # A still-running v0.8.17 client can update v1, but cannot overwrite v2.
        old['coins'] = 900
        self.files[0]['body'] = json.dumps({'schema': 1, 'saved_at': 200, 'save': old}).encode()
        self.files[0]['version'] = '2'
        envelope = device.download_save()
        self.assertEqual({envelope['save']['coins'], envelope['alternatives'][0]['save']['coins']}, {501, 900})


if __name__ == '__main__':
    unittest.main()
