"""Actual MP4 codecs, stream copying and failed-conversion preservation."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

@unittest.skipUnless(importlib.util.find_spec('yt_dlp') and shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Optional yt-dlp and FFmpeg required')
class MP4(unittest.TestCase):
    def test_final_flush_uses_writable_handle_and_preserves_real_io_errors(self):
        """Model Windows _commit access rules even when this suite runs on Linux."""
        import os
        real_open = Path.open
        real_sync = os.fsync
        access = {}
        def tracked_open(path, mode='r', *args, **kwargs):
            file = real_open(path, mode, *args, **kwargs)
            access[file.fileno()] = (path.name, mode)
            return file
        def windows_sync(fd):
            name, mode = access.get(fd, ('', ''))
            if name == 'output.mp4' and '+' not in mode and 'w' not in mode:
                raise OSError(9, 'Bad file descriptor')
            return real_sync(fd)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'clip.mkv'
            self.clip(source, 'libx264', 'aac')
            with patch.object(Path, 'open', tracked_open), patch('os.fsync', side_effect=windows_sync):
                _, info = self.processor().run({'filepath': str(source), 'ext': 'mkv'})
            self.assertTrue(Path(info['filepath']).is_file())
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'clip.mkv'
            self.clip(source, 'libx264', 'aac')
            with patch('os.fsync', side_effect=OSError(5, 'Disk flush failed')):
                with self.assertRaisesRegex(OSError, 'Disk flush failed'):
                    self.processor().run({'filepath': str(source), 'ext': 'mkv'})
            self.assertTrue(source.is_file())
            self.assertFalse(source.with_suffix('.mp4').exists())
    def clip(self, path, video, audio):
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=teal:s=160x90:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.3','-c:v',video,'-pix_fmt','yuv420p','-c:a',audio,str(path)],check=True)
    def processor(self):
        from yt_dlp import YoutubeDL
        from mdm.mp4_engine import CompatibleMP4PP
        return CompatibleMP4PP(YoutubeDL({'quiet':True}))
    def test_compatible_mp4_unchanged_and_mkv_remuxed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'compatible.mp4';self.clip(source,'libx264','aac');before=source.read_bytes()
            removed,info=self.processor().run({'filepath':str(source),'ext':'mp4'})
            self.assertEqual(removed,[]);self.assertEqual(source.read_bytes(),before)
            mkv=root/'compatible-mkv.mkv'
            subprocess.run(['ffmpeg','-v','error','-i',str(source),'-c','copy',str(mkv)],check=True)
            pp=self.processor()
            with patch.object(pp,'run_ffmpeg',wraps=pp.run_ffmpeg) as run:
                removed,info=pp.run({'filepath':str(mkv),'ext':'mkv'})
                options=run.call_args.args[2]
                self.assertEqual(options[options.index('-c:v')+1],'copy');self.assertEqual(options[options.index('-c:a')+1],'copy')
            self.assertEqual(Path(info['filepath']).suffix,'.mp4');self.assertEqual(removed,[str(mkv)])
    def test_webm_converted_to_h264_aac(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'clip.webm';self.clip(source,'libvpx-vp9','libopus')
            removed,info=self.processor().run({'filepath':str(source),'ext':'webm'})
            self.assertEqual(Path(info['filepath']).suffix,'.mp4')
            streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',info['filepath']]))['streams']
            self.assertEqual([s['codec_name'] for s in streams],['h264','aac'])
            self.assertEqual(streams[0]['pix_fmt'],'yuv420p');self.assertEqual(removed,[str(source)])
    def test_failed_conversion_keeps_input_and_removes_temporary_output(self):
        from yt_dlp.utils import PostProcessingError
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'clip.mp4';self.clip(source,'mpeg4','aac');before=source.read_bytes();pp=self.processor()
            def fail(src,dest,options):
                Path(dest).write_bytes(b'incomplete')
                raise PostProcessingError('Simulated encoder failure')
            with patch.object(pp,'run_ffmpeg',side_effect=fail),self.assertRaises(PostProcessingError):
                pp.run({'filepath':str(source),'ext':'mp4'})
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(list(Path(tmp).iterdir()),[source])
    def test_existing_mp4_is_not_overwritten(self):
        from yt_dlp.utils import PostProcessingError
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'clip.mkv';self.clip(source,'libx264','aac')
            target=source.with_suffix('.mp4');target.write_bytes(b'keep existing file')
            with self.assertRaisesRegex(PostProcessingError,'already exists'):
                self.processor().run({'filepath':str(source),'ext':'mkv'})
            self.assertEqual(target.read_bytes(),b'keep existing file');self.assertTrue(source.exists())

if __name__=='__main__':unittest.main()
