import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mdm_components
from mdm import tool_updater as tools
from mdm.service import Manager


class ToolUpdates(unittest.TestCase):
    def test_download_requires_exact_hash_and_size(self):
        data = b'validated archive'
        with tempfile.TemporaryDirectory() as tmp:
            for digest, size, valid in [(hashlib.sha256(data).hexdigest(), len(data), True), ('a'*64, len(data), False), (hashlib.sha256(data).hexdigest(), len(data)-1, False)]:
                path = Path(tmp)/'file'
                with patch.object(tools, 'open_url', return_value=io.BytesIO(data)):
                    if valid:
                        tools.download('https://github.com/a/b', path, digest, size, lambda _:None)
                        self.assertEqual(path.read_bytes(), data)
                    else:
                        with self.assertRaises(ValueError): tools.download('https://github.com/a/b', path, digest, size, lambda _:None)
                path.unlink(missing_ok=True)

    def test_external_hosts_and_insecure_redirects_rejected(self):
        for url in ['http://github.com/a', 'https://github.com.evil.test/a', 'https://user:pass@github.com/a', 'https://evil.test/a', 'https://github.com:8443/a']:
            with self.assertRaises(ValueError): tools.allowed_url(url)
        self.assertEqual(tools.allowed_url('https://release-assets.githubusercontent.com/a'), 'https://release-assets.githubusercontent.com/a')

    def test_github_release_requires_digest_and_matching_repository(self):
        asset = {'name':'deno-x86_64-pc-windows-msvc.zip','size':100,'digest':'sha256:'+'a'*64,
                 'browser_download_url':'https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip'}
        data = {'tag_name':'v2.9.7','assets':[asset]}
        with patch.object(tools,'read_json',return_value=data):
            self.assertEqual(tools.github_tool('Deno')['sha256'],'a'*64)
            asset['digest']=None
            with self.assertRaisesRegex(ValueError,'SHA-256'):tools.github_tool('Deno')
            asset['digest']='sha256:'+'a'*64
            asset['browser_download_url']=asset['browser_download_url'].replace('denoland','someone')
            with self.assertRaisesRegex(ValueError,'expected release'):tools.github_tool('Deno')

    def test_bundle_pointer_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(mdm_components,'DIRECTORY',Path(tmp)):
            p=Path(tmp)/'current.json'
            for name in ['../outside','C:\\other','/tmp/x','bundle-not-a-uuid']:
                p.write_text(json.dumps({'bundle':name}))
                self.assertIsNone(mdm_components.selected())

    def test_atomic_activation_retains_previous_bundle(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(mdm_components,'DIRECTORY',Path(tmp)),patch.object(mdm_components,'activate'):
            bundles=[]
            for n in ('a','b'):
                p=Path(tmp)/('bundle-'+n*32);(p/'packages').mkdir(parents=True);(p/'tools').mkdir();(p/'versions.json').write_text('{}');bundles.append(p)
            tools.activate_bundle(bundles[0]);tools.activate_bundle(bundles[1])
            data=json.loads((Path(tmp)/'current.json').read_text())
            self.assertEqual(data,{'bundle':bundles[1].name,'previous':bundles[0].name})
            self.assertTrue(bundles[0].exists())

    def test_archive_ignores_paths_and_requires_complete_windows_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'tool.zip';target=root/'tools';target.mkdir()
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../../ffmpeg.exe',b'MZtest')
            tools.unpack_tool(archive,target,['ffmpeg.exe'])
            self.assertEqual((target/'ffmpeg.exe').read_bytes(),b'MZtest')
            with self.assertRaises(ValueError):tools.unpack_tool(archive,target,['ffprobe.exe'])

    def manager(self):
        manager=Manager.__new__(Manager);manager.lock=threading.RLock();manager.active={};manager.analyses=0;manager.updating=False
        manager.tool_update={'busy':True};manager.tasks={'a':{'id':'a','status':'queued','start_at':123},'b':{'id':'b','status':'paused','start_at':0}}
        manager.save=lambda task:None
        return manager

    def test_failed_staging_leaves_queue_and_active_tools_untouched(self):
        manager=self.manager()
        with patch.object(tools,'stage',side_effect=RuntimeError('checksum')),patch.object(tools,'activate_bundle') as activate:
            manager.update_tools()
        activate.assert_not_called();self.assertEqual(manager.tasks['a']['status'],'queued');self.assertFalse(manager.updating);self.assertFalse(manager.tool_update['busy'])

    def test_switch_resumes_only_previously_running_queue(self):
        manager=self.manager()
        with tempfile.TemporaryDirectory() as tmp,patch('mdm.service.STATE',Path(tmp)),patch.object(tools,'stage',return_value=Path('candidate')),patch.object(tools,'activate_bundle'):
            manager.update_tools()
        self.assertEqual(manager.tasks['a']['status'],'queued');self.assertEqual(manager.tasks['a']['start_at'],123)
        self.assertEqual(manager.tasks['b']['status'],'paused');self.assertFalse(manager.updating);self.assertFalse(manager.tool_update['busy'])

    def test_activation_failure_restores_queue(self):
        manager=self.manager()
        with tempfile.TemporaryDirectory() as tmp,patch('mdm.service.STATE',Path(tmp)),patch.object(tools,'stage',return_value=Path('candidate')),patch.object(tools,'activate_bundle',side_effect=OSError('disk full')):
            manager.update_tools()
        self.assertEqual(manager.tasks['a']['status'],'queued');self.assertIn('disk full',manager.tool_update['error'])

    def test_up_to_date_does_not_pause_downloads(self):
        manager=self.manager()
        with patch.object(tools,'stage',return_value=None),patch.object(manager,'pause') as pause:
            manager.update_tools()
        pause.assert_not_called();self.assertFalse(manager.tool_update['busy'])


if __name__=='__main__':unittest.main()
