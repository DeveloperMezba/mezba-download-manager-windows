"""Optional yt-dlp and Google Drive integrations; no shell execution."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from .common import BASE, url_checked
from .platform_support import hidden_process, stop_process_tree, worker_python
from .http_engine import DownloadError, Paused

ANALYZE_LOCK = threading.BoundedSemaphore(2)

def module_cmd(name):
    if importlib.util.find_spec(name) is None:
        raise DownloadError(f'{name} is missing from MDM. Run the Windows installer again to repair it.')
    return [worker_python(), '-X', 'utf8', '-m', name]

def engine_error(details, code):
    details = details[-2200:]
    lower = details.lower()
    if any(marker in lower for marker in ('could not copy chrome cookie database',
            'failed to decrypt with dpapi', 'could not find chrome cookies database',
            'could not find brave cookies database')):
        return ('MDM could not read the selected browser sign-in session. For public videos, '
                'set Preferences > Signed-in browser session to Off and retry. If sign-in is '
                'required, try a supported Firefox session. A locked or encrypted Chrome/Brave '
                'cookie database cannot be used.\n\n' + details)
    # Always retain the exit code, even when the last lines only report a filename.
    return f'Download engine failed (exit code {code}).\n' + (details or 'No diagnostic output was returned.')


def runtime_args():
    for name, minimum in (('deno', (2, 3, 0)), ('node', (22, 0, 0))):
        if not shutil.which(name):
            continue
        try:
            version = subprocess.check_output([name, '--version'], text=True, timeout=5, **hidden_process())
            match = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
            if match and tuple(map(int, match.groups())) >= minimum:
                return ['--no-js-runtimes', '--js-runtimes', name]
        except (OSError, subprocess.SubprocessError):
            pass
    if shutil.which('qjs'):
        return ['--no-js-runtimes', '--js-runtimes', 'quickjs']
    return []

def ytdlp_base(settings):
    args = module_cmd('yt_dlp') + ['--ignore-config', '--no-colors',
            '--socket-timeout', '20', '--no-warnings'] + runtime_args()
    if settings.get('cookies_browser'):
        args += ['--cookies-from-browser', settings['cookies_browser']]
    return args

def choices(info):
    formats = [f for f in info.get('formats', []) if not f.get('has_drm')]
    if info.get('has_drm'):
        raise DownloadError('This video is DRM protected; MDM cannot download it.')
    heights = sorted({int(f['height']) for f in formats if f.get('height') and f.get('vcodec') != 'none'}, reverse=True)
    result = []
    if any(f.get('vcodec') != 'none' for f in formats):
        result += [{'id': 'best', 'label': 'MKV · Best available video + audio'},
                   {'id': 'mp4:best', 'label': 'MP4 · Best available video + audio (H.264/AAC)'}]
    for h in heights[:30]:
        label = f'{h}p' + (' · 4K' if h == 2160 else ' · 8K' if h == 4320 else '')
        result += [{'id': f'v:{h}', 'label': 'MKV · ' + label + ' + audio'},
                   {'id': f'mp4:v:{h}', 'label': 'MP4 · ' + label + ' + audio (H.264/AAC)'}]
    if any(f.get('acodec') != 'none' for f in formats):
        result += [{'id': 'audio', 'label': 'Audio only · original quality'},
                   {'id': 'mp3', 'label': 'Audio only · MP3 (conversion)'}]
    if not result:
        raise DownloadError('No downloadable formats found for this video.')
    return result

def inspect_json(url, base, flags, timeout):
    cmd = base + flags + ['--dump-single-json', '--skip-download', '--', url_checked(url)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **hidden_process())
    except subprocess.TimeoutExpired as e:
        raise DownloadError('Inspection timed out. Try the direct video or playlist page.') from e
    if result.returncode:
        raise DownloadError(engine_error(result.stderr.strip(), result.returncode))
    return json.loads(result.stdout)


def positive_int(value):
    try:
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def analyze(url, settings):
    if not ANALYZE_LOCK.acquire(False):
        raise DownloadError('Two videos are already being inspected. Please try again shortly.')
    try:
        url = url_checked(url)
        base = ytdlp_base(settings)
        playlist = None
        warning = ''
        # Flat extraction visits at most one entry; it never resolves every song
        # just to populate a menu. A watch URL can expose both item and playlist.
        try:
            flat = inspect_json(url, base, ['--yes-playlist', '--flat-playlist', '--playlist-items', '1'], 30)
            if flat.get('_type') == 'playlist':
                playlist = {'url': url, 'title': str(flat.get('title') or 'Playlist')[:300],
                            'count': positive_int(flat.get('playlist_count'))}
        except (DownloadError, ValueError):
            warning = 'Playlist detection was unavailable. Only confirmed item choices are shown.'
        info = None
        single_url = url
        is_first = False
        try:
            raw = inspect_json(url, base, ['--no-playlist', '--playlist-items', '1'], 65)
            if raw.get('_type') in ('playlist', 'multi_video'):
                is_first = True
                if raw.get('_type') == 'playlist' and playlist is None:
                    playlist = {'url': url, 'title': str(raw.get('title') or 'Playlist')[:300],
                                'count': positive_int(raw.get('playlist_count'))}
                    warning = ''
                info = next((entry for entry in raw.get('entries', []) if entry), None)
                if not info:
                    raise DownloadError('The first playlist item is unavailable.')
                candidate = info.get('webpage_url') or info.get('original_url') or info.get('url')
                if candidate:
                    try:
                        single_url = url_checked(candidate)
                    except ValueError:
                        pass  # --playlist-items 1 also constrains the original URL.
            else:
                info = raw
            item_choices = choices(info)
        except (DownloadError, ValueError) as error:
            if not playlist:
                raise
            info, item_choices = None, []
            warning = 'The preview item is unavailable. Full-playlist modes are still offered; inaccessible items will be reported.'
        title = str((info or {}).get('title') or (playlist or {}).get('title') or 'Video')[:300]
        result = []
        group = 'First item only' if is_first else 'This item only'
        for choice in item_choices:
            result.append({**choice, 'label': group + ' · ' + choice['label'],
                           'group': group, 'url': single_url, 'title': title})
        if playlist:
            modes = [('best', 'MKV video · best available'), ('mp4:best', 'MP4 video · best available (H.264/AAC)'), ('audio', 'Audio · original quality'),
                     ('mp3', 'Audio · MP3')]
            # These are quality ceilings applied independently to every item,
            # never a claim that every playlist item has the sampled resolution.
            for choice in item_choices:
                if choice['id'].startswith('v:'):
                    modes.append((choice['id'], 'MKV video · up to ' + choice['id'][2:] + 'p'))
                elif choice['id'].startswith('mp4:v:'):
                    modes.append((choice['id'], 'MP4 video · up to ' + choice['id'][6:] + 'p (H.264/AAC)'))
            for mode, description in modes:
                result.append({'id': 'playlist:' + mode, 'label': 'Full playlist · ' + description,
                               'group': 'Full playlist', 'url': playlist['url'], 'title': playlist['title']})
        return {'title': title, 'choices': result, 'playlist': playlist, 'warning': warning,
                'live': bool((info or {}).get('is_live')), 'first_item': is_first}
    finally:
        ANALYZE_LOCK.release()


def split_choice(choice):
    if not isinstance(choice, str):
        raise ValueError('Unknown quality selection')
    playlist = choice.startswith('playlist:')
    quality = choice[len('playlist:'):] if playlist else choice
    format_args(quality)
    return playlist, quality


def media_command(task, settings):
    folder = Path(task['folder'])
    playlist, quality = split_choice(task['quality'])
    selection = ['--yes-playlist', '--no-abort-on-error'] if playlist else ['--no-playlist', '--playlist-items', '1']
    output = '%(playlist_index)05d - %(title).140B [%(id)s].%(ext)s' if playlist else '%(title).140B [%(id)s].%(ext)s'
    base = ytdlp_base(settings)
    if quality.startswith('mp4:'):
        # Run compatibility conversion before yt-dlp records playlist completion.
        base = [worker_python(), '-X', 'utf8', str(BASE / 'mdm/mp4_engine.py')] + base[5:]
    cmd = base + selection + ['--continue', '--no-overwrites', '--newline', '--progress',
           '--no-simulate', '--retries', str(settings['retries']), '--fragment-retries', str(settings['retries']),
           '--retry-sleep', 'exp=1:30', '--concurrent-fragments', str(min(4, settings['connections'])),
           '--paths', str(folder), '--output', output,
           '--merge-output-format', 'mkv', '--progress-template',
           'download:MDM_PROGRESS %(progress)j', '--print', 'after_move:MDM_FILE %(filepath)j']
    if not quality.startswith('mp4:') and quality not in ('audio', 'mp3'):
        cmd += ['--remux-video', 'mkv']
    if playlist:
        cmd += ['--download-archive', str(folder / '.mdm-playlist-archive.txt'),
                '--print', 'before_dl:MDM_ITEM %(playlist_index)j\t%(playlist_count,n_entries)j\t%(title)j']
    if settings['speed_kib']:
        cmd += ['--limit-rate', f"{settings['speed_kib']}K"]
    return cmd + format_args(quality) + ['--', task['url']]

def format_args(choice):
    if isinstance(choice, str) and choice.startswith('mp4:'):
        video = choice[4:]
        if video != 'best' and not re.fullmatch(r'v:[1-9]\d{1,4}', video):
            raise ValueError('Unknown MP4 video selection')
        # Favor compatibility at equal resolution; preserve the requested quality ceiling.
        return format_args(video) + ['-S', 'res,vcodec:h264,acodec:aac']
    if choice == 'best':
        return ['-f', 'bv*+ba/b']
    if re.fullmatch(r'v:[1-9]\d{1,4}', choice):
        h = int(choice[2:])
        return ['-f', f'bv*[height<={h}]+ba/b[height<={h}]']
    if choice in ('audio', 'mp3'):
        return ['-f', 'ba/b', '-x', '--audio-format', 'mp3' if choice == 'mp3' else 'best']
    raise ValueError('Unknown quality selection')

def run_external(task, settings, stop, progress, item_progress=None):
    folder = Path(task['folder'])
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if task['kind'] == 'drive':
        module_cmd('gdown')  # Check dependency before launching the helper.
        cmd = [worker_python(), '-X', 'utf8', str(BASE / 'mdm/drive.py'), task['url'],
               str(folder), task['filename'], str(settings['speed_kib']), str(settings['retries'])]
    else:
        if not shutil.which('ffmpeg'):
            raise DownloadError('FFmpeg is missing. Run the MDM Windows installer again and let the media-tool setup finish.')
        cmd = media_command(task, settings)
    # Supervisor terminates the process group if the service crashes.
    proc = subprocess.Popen([worker_python(), '-X', 'utf8', str(BASE / 'mdm/child.py'), str(os.getpid()), *cmd],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            start_new_session=True, bufsize=1, **hidden_process())
    tail, files = [], []
    terminated = threading.Event()
    def watcher():
        while proc.poll() is None:
            if stop.wait(0.2):
                stop_process_tree(proc)
                try:
                    proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    stop_process_tree(proc)
                terminated.set()
                return
    threading.Thread(target=watcher, daemon=True).start()
    for line in proc.stdout:
        line = line.strip()
        if line.startswith('MDM_PROGRESS '):
            try:
                p = json.loads(line[len('MDM_PROGRESS '):])
                progress(p.get('downloaded_bytes') or 0,
                         p.get('total_bytes') or p.get('total_bytes_estimate'), p.get('speed') or 0)
            except (ValueError, TypeError):
                pass
        elif line.startswith('MDM_ITEM ') and item_progress:
            try:
                index, count, title = [json.loads(v) for v in line[len('MDM_ITEM '):].split('\t', 2)]
                item_progress(positive_int(index), positive_int(count), str(title)[:300])
            except (ValueError, TypeError):
                pass
        elif line.startswith('MDM_FILE '):
            try:
                files[:] = [json.loads(line[len('MDM_FILE '):])]  # Bounded memory for long playlists
            except ValueError:
                pass
        elif line:
            tail = (tail + [line])[-12:]
    proc.stdout.close()
    result = proc.wait()
    if stop.is_set() or terminated.is_set():
        raise Paused('Paused; engine partial files retained.')
    if result:
        raise DownloadError(engine_error('\n'.join(tail), result))
    if task['kind'] == 'drive':
        path = Path(files[-1]) if files else folder / task['filename']
        if not path.is_file():
            raise DownloadError('Drive returned no file.')
        progress(path.stat().st_size, path.stat().st_size, 0)
        return str(path)
    if task['quality'].startswith('playlist:'):
        archive = folder / '.mdm-playlist-archive.txt'
        if files or (archive.is_file() and archive.stat().st_size):
            return str(folder)
        raise DownloadError('No playlist items were downloaded. Check the playlist and your access.')
    if not files:
        raise DownloadError('Video engine reported no final output. Check the task folder before retrying.')
    path = Path(files[-1])
    if not path.is_file():
        raise DownloadError('The engine reported completion, but the final file is missing. Check the task folder.')
    size = path.stat().st_size
    progress(size, size, 0)
    return str(path)
