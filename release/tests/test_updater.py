import hashlib
import json
import shutil
import tempfile
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from update_core import Installer, UpdateError, extract, manifest, version, download

REPO='badbed7/morning-bloom'

class Updating(unittest.TestCase):
    def payload(self, root, release='0.3.0', name='MorningBloomGame.exe', python_mode=False):
        archive=root/(release+'.zip')
        with zipfile.ZipFile(archive,'w') as z:
            if python_mode:
                z.writestr('release/game_entry.py', b'# Python game')
                z.writestr('python/morning_bloom/__main__.py', b'# game entry')
                z.writestr('python/requirements.txt', b'PySide6==6.8.3')
            else:
                z.writestr(name,b'fake-executable-for-test')
        asset = 'MorningBloom-python.zip' if python_mode else 'MorningBloom-game.zip'
        data=dict(protocol=1,version=release,size=archive.stat().st_size,
            sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            url=f'https://github.com/{REPO}/releases/download/v{release}/{asset}')
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

    def test_latest_checked_before_install_and_both_modes_preserve_saves(self):
        from launcher import prepare
        for python_mode in (False, True):
            with self.subTest(python_mode=python_mode), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);installer=Installer(root/'launcher', python_mode)
                saves=root/'MorningBloomPython';saves.mkdir()
                (saves/'garden.json').write_bytes(b'actual player save')
                archive,old=self.payload(root, python_mode=python_mode)
                installer.install(archive,old,lambda _:True)
                latest_archive,latest=self.payload(root,'0.4.0',python_mode=python_mode)
                order=[]
                def fetch(repository, mode):
                    self.assertEqual((repository, mode), (REPO, python_mode))
                    order.append('check')
                    return latest
                def get_zip(data, path, report):
                    order.append('download');shutil.copyfile(latest_archive,path)
                def healthy(*args):
                    order.append('health');return True
                with patch('launcher.read_latest',side_effect=fetch), patch('launcher.download',side_effect=get_zip), \
                        patch('launcher.python_runtime',return_value=Path('python.exe')), patch('launcher.health_check',side_effect=healthy):
                    result=prepare(installer,root,lambda _:None)
                    self.assertEqual(order,['check','download','health'])
                    self.assertEqual(installer.current()['version'],'0.4.0')
                    self.assertTrue(result.is_file())
                    order.clear()
                    prepare(installer,root,lambda _:None)
                    self.assertEqual(order,['check'])
                self.assertEqual((saves/'garden.json').read_bytes(),b'actual player save')

    def test_first_launch_online_without_bundle_and_invalid_download_fallback(self):
        from launcher import prepare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher')
            archive,data=self.payload(root)
            with patch('launcher.read_latest',return_value=data), \
                    patch('launcher.download',side_effect=lambda data,path,report:shutil.copyfile(archive,path)), \
                    patch('launcher.health_check',return_value=True):
                self.assertTrue(prepare(installer,root,lambda _:None).is_file())
            _,new=self.payload(root,'0.4.0')
            for failure in (OSError('offline'), UpdateError('hash mismatch')):
                with patch('launcher.read_latest',return_value=new), patch('launcher.download',side_effect=failure):
                    prepare(installer,root,lambda _:None)
                self.assertEqual(installer.current()['version'],'0.3.0')
                self.assertIn(str(failure),(installer.root/'update.log').read_text(encoding='utf-8'))

    def test_identical_bundle_avoids_download_after_check(self):
        from launcher import prepare
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);installer=Installer(root/'launcher');archive,data=self.payload(root)
            archive.rename(root/'MorningBloom-game.zip')
            (root/'bundled-update.json').write_text(json.dumps(data))
            with patch('launcher.read_latest',return_value=data) as latest, patch('launcher.download') as get_zip, \
                    patch('launcher.health_check',return_value=True):
                prepare(installer,root,lambda _:None)
            latest.assert_called_once();get_zip.assert_not_called()

    def test_python_runtime_cache_and_failed_dependency_upgrade(self):
        from launcher import python_runtime
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entry=root/'game/release/game_entry.py'
            entry.parent.mkdir(parents=True);(root/'game/python').mkdir()
            requirements=root/'game/python/requirements.txt';requirements.write_text('PySide6==6.8.3')
            def setup(args, **kwargs):
                if 'venv' in args:
                    exe=Path(args[-1])/'Scripts/python.exe';exe.parent.mkdir(parents=True);exe.touch()
            with patch('launcher.subprocess.run',side_effect=setup) as run:
                first=python_runtime(entry,root,lambda _:None)
                self.assertEqual(python_runtime(entry,root,lambda _:None),first)
                self.assertEqual(run.call_count,2)
            requirements.write_text('PySide6==9.0.0')
            with patch('launcher.subprocess.run',side_effect=OSError('offline')), self.assertRaises(UpdateError):
                python_runtime(entry,root,lambda _:None)
            requirements.write_text('PySide6==6.8.3')
            with patch('launcher.subprocess.run') as run:
                self.assertEqual(python_runtime(entry,root,lambda _:None),first)
                run.assert_not_called()

    def test_python_feed_cannot_accept_native_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive,data=self.payload(root)
            with self.assertRaises(UpdateError):manifest(data,REPO,True)
            with self.assertRaises(UpdateError):extract(archive,root/'unpack',True)

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
