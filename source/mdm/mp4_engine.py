"""yt-dlp worker: finalize MP4 as H.264/AAC before recording archive success."""
import os
from pathlib import Path
import sys
import tempfile
import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import PostProcessingError


def compatible(streams):
    video = next((s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    return video, audio, bool(video and video.get('codec_name') == 'h264' and video.get('pix_fmt') == 'yuv420p'), bool(not audio or audio.get('codec_name') == 'aac')


class CompatibleMP4PP(FFmpegPostProcessor):
    def run(self, info):
        source = Path(info['filepath'])
        streams = self.get_metadata_object(str(source)).get('streams', [])
        video, audio, video_ok, audio_ok = compatible(streams)
        if not video:
            raise PostProcessingError('MP4 video needs a video stream. Choose an audio-only option for this source.')
        if source.suffix.lower() == '.mp4' and video_ok and audio_ok:
            return [], info
        target = source.with_suffix('.mp4')
        if target != source and target.exists():
            raise PostProcessingError('An MP4 output already exists. Keep it or choose a new download task; MDM will not overwrite it.')
        self.to_screen('Preparing compatible MP4. ' + ('Copying streams.' if video_ok and audio_ok else 'Converting to H.264/AAC; this may take time.'))
        # Stage next to the source so promotion is atomic; incomplete conversion
        # never replaces source data. A retry restarts conversion, not the download.
        with tempfile.TemporaryDirectory(prefix='.mdm-mp4-', dir=source.parent) as stage:
            output = Path(stage) / 'output.mp4'
            options = ['-map', '0:'+str(video['index'])]
            if audio:options += ['-map', '0:'+str(audio['index'])]
            options += ['-c:v', 'copy'] if video_ok else ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-threads', '2']
            if audio:options += ['-c:a', 'copy'] if audio_ok else ['-c:a', 'aac', '-b:a', '192k']
            options += ['-movflags', '+faststart']
            self.run_ffmpeg(str(source), str(output), options)
            _, _, output_video_ok, output_audio_ok = compatible(self.get_metadata_object(str(output)).get('streams', []))
            if not output_video_ok or not output_audio_ok:
                raise PostProcessingError('MP4 codec verification failed; the original downloaded file was kept.')
            # Windows _commit/FlushFileBuffers requires a writable handle.
            # Read-only flushes fail with EBADF after conversion reaches 100%.
            with output.open('r+b') as file:os.fsync(file.fileno())
            if target == source:
                os.replace(output, target)
            else:
                # Atomic no-clobber publication, including a concurrent file creation.
                if os.name == 'nt':os.rename(output,target)
                else:os.link(output,target);output.unlink()
            if os.name != 'nt':
                fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
        info['filepath'] = str(target)
        info['ext'] = 'mp4'
        info['format'] = 'mp4'
        return ([] if target == source else [str(source)]), info


def main():
    parsed = yt_dlp.parse_options(sys.argv[1:])
    with yt_dlp.YoutubeDL(parsed.ydl_opts) as downloader:
        downloader.add_post_processor(CompatibleMP4PP(downloader), when='post_process')
        return downloader.download(parsed.urls)


if __name__ == '__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
    except yt_dlp.utils.DownloadError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
