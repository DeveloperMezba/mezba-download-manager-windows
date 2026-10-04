"""Optional real-engine smoke test, using a generated local clip, not live websites."""
import functools
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mdm import media
from mdm.common import DEFAULTS

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*_):pass

@unittest.skipUnless(importlib.util.find_spec('yt_dlp') and shutil.which('ffmpeg'), 'Optional yt-dlp and FFmpeg required')
class RealMedia(unittest.TestCase):
    def test_inspect_download_and_audio_conversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=teal:s=320x180:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','1','-c:v','mpeg4','-c:a','aac',str(root/'clip.mp4')],check=True)
            server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root)))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                url=f'http://127.0.0.1:{server.server_port}/clip.mp4'
                info=media.analyze(url,DEFAULTS)
                self.assertIn('best',[c['id'] for c in info['choices']])
                for quality in ('best','mp3','mp4:best'):
                    task={'kind':'media','quality':quality,'url':url,'folder':str(root/quality.replace(':','-'))}
                    output=media.run_external(task,DEFAULTS,threading.Event(),lambda *_:None)
                    self.assertTrue(Path(output).is_file())
                    result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',output],capture_output=True,text=True,check=True)
                    kinds=[s['codec_type'] for s in json.loads(result.stdout)['streams']]
                    self.assertIn('audio',kinds)
                    if quality in ('best','mp4:best'):self.assertIn('video',kinds)
                    if quality=='best':self.assertEqual(Path(output).suffix,'.mkv')
                    if quality=='mp4:best':
                        self.assertEqual(Path(output).suffix,'.mp4')
                        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',output]))
                        self.assertEqual([s['codec_name'] for s in probe['streams']],['h264','aac'])
                    if quality=='mp3':self.assertEqual(kinds,['audio'])
            finally:
                server.shutdown();server.server_close()

    def test_playlist_modes_archive_and_partial_failure(self):
        from mdm.http_engine import DownloadError
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=teal:s=320x180:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','0.4','-c:v','mpeg4','-c:a','aac',str(root/'a.mp4')],check=True)
            shutil.copy2(root/'a.mp4',root/'b.mp4')
            (root/'list.html').write_text('<html><head><title>Local music collection</title></head><body><video src="/a.mp4"></video><video src="/b.mp4"></video></body></html>')
            server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root)))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            settings={**DEFAULTS,'retries':0}
            try:
                url=f'http://127.0.0.1:{server.server_port}/list.html'
                info=media.analyze(url,settings)
                self.assertEqual(info['playlist']['count'],2)
                self.assertTrue(info['first_item'])
                self.assertIn('playlist:mp3',[c['id'] for c in info['choices']])
                for quality,expected in [('best',1),('playlist:best',2),('playlist:mp3',2),('playlist:mp4:best',2)]:
                    folder=root/quality.replace(':','-')
                    events=[]
                    task={'kind':'media','quality':quality,'url':url,'folder':str(folder)}
                    media.run_external(task,settings,threading.Event(),lambda *_:None,lambda *args:events.append(args))
                    files=[p for p in folder.iterdir() if not p.name.startswith('.')]
                    self.assertEqual(len(files),expected)
                    for file in files:
                        probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(file)],capture_output=True,text=True,check=True)
                        types=[s['codec_type'] for s in json.loads(probe.stdout)['streams']]
                        if quality=='playlist:mp3':self.assertEqual(types,['audio'])
                        else:self.assertIn('video',types)
                        if quality=='playlist:mp4:best':
                            self.assertEqual(file.suffix,'.mp4')
                            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(file)]))
                            self.assertEqual([s['codec_name'] for s in probe['streams']],['h264','aac'])
                    if expected==2:
                        self.assertEqual([e[0] for e in events],[1,2])
                        self.assertEqual(sorted(p.name[:5] for p in files),['00001','00002'])
                        stamps={p.name:p.stat().st_mtime_ns for p in files}
                        media.run_external(task,settings,threading.Event(),lambda *_:None)
                        self.assertEqual(stamps,{p.name:p.stat().st_mtime_ns for p in files})
                # One unavailable item must not turn an incomplete playlist green.
                (root/'b.mp4').unlink()
                task={'kind':'media','quality':'playlist:mp3','url':url,'folder':str(root/'partial')}
                with self.assertRaises(DownloadError):
                    media.run_external(task,settings,threading.Event(),lambda *_:None)
                saved=list((root/'partial').glob('*.mp3'))
                self.assertEqual(len(saved),1)
                stamp=saved[0].stat().st_mtime_ns
                shutil.copy2(root/'a.mp4',root/'b.mp4')
                media.run_external(task,settings,threading.Event(),lambda *_:None)
                self.assertEqual(len(list((root/'partial').glob('*.mp3'))),2)
                self.assertEqual(saved[0].stat().st_mtime_ns,stamp)
            finally:
                server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
