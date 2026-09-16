import hashlib
import json
import tempfile
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from update_core import Installer, UpdateError, extract, manifest, version, download

REPO='badbed7/morning-bloom-releases'

class Updating(unittest.TestCase):
    def payload(self, root, release='0.3.0', name='MorningBloomGame.exe'):
        archive=root/(release+'.zip')
        with zipfile.ZipFile(archive,'w') as z: z.writestr(name,b'fake-executable-for-test')
        data=dict(protocol=1,version=release,size=archive.stat().st_size,
            sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            url=f'https://github.com/{REPO}/releases/download/v{release}/MorningBloom-game.zip')
        return archive,data

    def test_upgrade_and_save_directory_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);saves=root/'MorningBloomPython';saves.mkdir();(saves/'garden.json').write_text('original')
            installer=Installer(root/'launcher')
            a,first=self.payload(root);installer.install(a,first,lambda _:True)
            b,second=self.payload(root,'0.4.0');installer.install(b,second,lambda _:True)
            self.assertEqual(installer.current()['version'],'0.4.0')
            self.assertEqual(json.loads((installer.root/'previous.json').read_text())['version'],'0.3.0')
            self.assertTrue(installer.executable(first).exists())
            self.assertEqual((saves/'garden.json').read_text(),'original')

    def test_bad_hash_keeps_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher')
            a,data=self.payload(root);installer.install(a,data,lambda _:True)
            b,new=self.payload(root,'0.4.0');b.write_bytes(b'corrupt')
            with self.assertRaises(UpdateError):installer.install(b,new,lambda _:True)
            self.assertEqual(installer.current()['version'],'0.3.0')

    def test_failed_health_check_keeps_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher')
            a,data=self.payload(root);installer.install(a,data,lambda _:True)
            b,new=self.payload(root,'0.4.0')
            with self.assertRaises(UpdateError):installer.install(b,new,lambda _:False)
            self.assertEqual(installer.current()['version'],'0.3.0')
            self.assertFalse(installer.folder(new).exists())

    def test_downgrade_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher')
            a,data=self.payload(root,'0.4.0');installer.install(a,data,lambda _:True)
            b,new=self.payload(root,'0.3.0')
            with self.assertRaises(UpdateError):installer.install(b,new,lambda _:True)

    def test_unsafe_archive_paths_rejected(self):
        for name in ['../escape.exe','/escape.exe','C:/escape.exe','x\\escape.exe','x:stream','NUL.txt','a./file']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);a,_=self.payload(root,name=name)
                with self.assertRaises(UpdateError):extract(a,root/'unpack')

    def test_manifest_origin_protocol_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,data=self.payload(Path(tmp))
            self.assertEqual(manifest(data,REPO),data)
            for key,value in [('url','https://evil.example/game.zip'),('protocol',2),('sha256','bad'),('size',-1),('version','../../escape')]:
                with self.subTest(key=key),self.assertRaises(UpdateError):manifest({**data,key:value},REPO)
            self.assertGreater(version('0.10.0'),version('0.9.0'))

    def test_offline_launcher_uses_current(self):
        from launcher import prepare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher')
            a,data=self.payload(root);installer.install(a,data,lambda _:True)
            with patch('launcher.read_latest',side_effect=OSError('offline')):
                result=prepare(installer,root,lambda _:None)
            self.assertEqual(result,installer.executable(installer.current()))

    def test_first_launch_offline_installs_bundle(self):
        from launcher import prepare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher');a,data=self.payload(root)
            a.rename(root/'MorningBloom-game.zip');(root/'bundled-update.json').write_text(json.dumps(data))
            with patch('launcher.read_latest',side_effect=OSError('offline')),patch('launcher.health_check',return_value=True):
                result=prepare(installer,root,lambda _:None)
            self.assertTrue(result.exists())

    def test_duplicate_archive_names_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'dup.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('MorningBloomGame.exe',b'a');z.writestr('morningbloomgame.exe',b'b')
            with self.assertRaises(UpdateError):extract(archive,root/'unpack')

    def test_offline_bundle_upgrade_and_fallback(self):
        from launcher import prepare
        for bundled,healthy,expected in [('0.4.0',True,'0.4.0'),('0.4.0',False,'0.3.0'),('0.2.0',True,'0.3.0')]:
            with self.subTest(bundled=bundled,healthy=healthy),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);installer=Installer(root/'launcher')
                archive,current=self.payload(root);installer.install(archive,current,lambda _:True)
                archive,data=self.payload(root,bundled);archive.rename(root/'MorningBloom-game.zip')
                (root/'bundled-update.json').write_text(json.dumps(data))
                with patch('launcher.read_latest',side_effect=OSError('offline')),patch('launcher.health_check',return_value=healthy):
                    result=prepare(installer,root,lambda _:None)
                self.assertEqual(installer.current()['version'],expected)
                self.assertEqual(result,installer.executable(installer.current()))

    def test_download_failure_removes_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,data=self.payload(root);target=root/'partial.zip';target.write_bytes(b'partial')
            with patch('urllib.request.urlopen',side_effect=OSError('offline')):
                with self.assertRaises(OSError):download(data,target)
            self.assertFalse(target.exists())

    def test_startup_failure_preserves_diagnostic_and_current_install(self):
        from launcher import health_check
        for result in [subprocess.CompletedProcess([], 0xc0000135), subprocess.TimeoutExpired([],45), OSError('launch denied')]:
            with self.subTest(result=result),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);installer=Installer(root/'launcher')
                archive,current=self.payload(root);installer.install(archive,current,lambda _:True)
                archive,data=self.payload(root,'0.4.1');log=installer.root/'startup-check.log'
                def failed_run(*args,**kwargs):
                    self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
                    self.assertEqual(kwargs['cwd'],Path(args[0][0]).parent)
                    kwargs['stderr'].write('native loader diagnostic\n')
                    if isinstance(result,Exception): raise result
                    return result
                with patch('launcher.subprocess.run',side_effect=failed_run),self.assertRaisesRegex(UpdateError,'Diagnostic log:'):
                    installer.install(archive,data,lambda exe:health_check(exe,log))
                self.assertIn('native loader diagnostic',log.read_text(encoding='utf-8'))
                self.assertEqual(installer.current()['version'],current['version'])
                self.assertFalse(installer.folder(data).exists())

    def test_windowed_game_exception_is_logged(self):
        from game_entry import checked_smoke_test
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'startup.log'
            with patch('game_entry.smoke_test',side_effect=ImportError('missing test runtime')):
                self.assertEqual(checked_smoke_test(log),1)
            self.assertIn('ImportError: missing test runtime',log.read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
