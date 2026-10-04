"""Manual, staged tool updates. Only an entirely verified bundle is activated."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile

import mdm_components
from .common import BASE, atomic_json
from .platform_support import hidden_process, worker_python, WINDOWS
from . import __version__

MAX_DOWNLOAD = 350 * 1024 * 1024
REPOSITORIES = {'Deno': ('denoland/deno', r'deno-x86_64-pc-windows-msvc\.zip', ['deno.exe']),
                'FFmpeg': ('GyanD/codexffmpeg', r'ffmpeg-[0-9.]+-essentials_build\.zip', ['ffmpeg.exe', 'ffprobe.exe'])}
ALLOWED_HOSTS = {'pypi.org', 'files.pythonhosted.org', 'api.github.com', 'github.com'}


def allowed_url(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != 'https' or p.username or p.password or p.port not in (None, 443)
            or not (p.hostname in ALLOWED_HOSTS or (p.hostname or '').endswith('.githubusercontent.com'))):
        raise ValueError('Unexpected tool download address')
    return url


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, allowed_url(newurl))


def open_url(url):
    req = urllib.request.Request(allowed_url(url), headers={'User-Agent': 'MDM-Windows/' + __version__})
    return urllib.request.build_opener(Redirects()).open(req, timeout=60)


def read_json(url):
    with open_url(url) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('Tool metadata is too large')
    return json.loads(raw)


def download(url, target, digest, size, progress):
    if not re.fullmatch('[a-fA-F0-9]{64}', digest or '') or not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
        raise ValueError('Tool package needs a valid SHA-256 and size')
    done = 0
    checksum = hashlib.sha256()
    with open_url(url) as response, target.open('xb') as output:
        while True:
            block = response.read(256 * 1024)
            if not block:
                break
            done += len(block)
            if done > size:
                raise ValueError('Tool package exceeds its announced size')
            output.write(block)
            checksum.update(block)
            progress(done / size)
    if done != size or checksum.hexdigest() != digest.lower():
        raise ValueError('Tool checksum failed. The current tools were kept.')


def github_tool(label):
    repo, pattern, executables = REPOSITORIES[label]
    release = read_json('https://api.github.com/repos/' + repo + '/releases/latest')
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('A stable ' + label + ' release was not found')
    assets = [a for a in release.get('assets', []) if re.fullmatch(pattern, a.get('name', ''))]
    if len(assets) != 1:
        raise ValueError('The ' + label + ' release layout changed. Current tools were kept.')
    asset = assets[0]
    expected_path = '/' + repo + '/releases/download/' + release['tag_name'] + '/' + asset['name']
    p = urllib.parse.urlsplit(asset['browser_download_url'])
    if p.netloc != 'github.com' or urllib.parse.unquote(p.path) != expected_path or p.query or p.fragment:
        raise ValueError('Tool asset does not belong to the expected release')
    digest = asset.get('digest') or ''
    if not re.fullmatch('sha256:[a-fA-F0-9]{64}', digest):
        raise ValueError(label + ' has no upstream SHA-256. Current tools were kept.')
    return {'label': label, 'version': release['tag_name'], 'url': asset['browser_download_url'],
            'sha256': digest[7:], 'size': asset['size'], 'executables': executables}


def inventory():
    result = {}
    bundle = mdm_components.selected()
    paths = ([str(bundle / 'packages')] if bundle else []) + sys.path
    for name in ('yt-dlp', 'yt-dlp-ejs', 'gdown'):
        normalized = name.replace('-', '_')
        result[name] = 'Not installed'
        for dist in importlib.metadata.distributions(path=paths):
            if dist.metadata.get('Name', '').lower().replace('-', '_') == normalized:
                result[name] = dist.version
                break
    for label, (_, _, executables) in REPOSITORIES.items():
        directory = bundle / 'tools' if bundle else BASE.parent / 'tools'
        executable = directory / executables[0]
        try:
            output = subprocess.check_output([str(executable), '--version' if label == 'Deno' else '-version'],
                       timeout=10, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', **hidden_process())
            match = re.search(r'(?:deno|ffmpeg version)\s+(\S+)', output)
            result[label] = label + ' ' + (match[1] if match else output.splitlines()[0][:60])
        except (OSError, subprocess.SubprocessError):
            result[label] = 'Not installed'
    return result


def run_checked(command, log, timeout=600, env=None):
    # Use the existing supervisor so a service crash cannot orphan pip/FFmpeg.
    wrapped = [worker_python(), '-X', 'utf8', str(BASE / 'mdm/child.py'), str(os.getpid()), *command]
    with log.open('ab') as output:
        process = subprocess.Popen(wrapped, stdout=output, stderr=output, stdin=subprocess.DEVNULL,
                                   start_new_session=True, env=env, **hidden_process())
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            from .platform_support import stop_process_tree
            stop_process_tree(process)
            process.wait(timeout=15)
            raise RuntimeError('Tool update timed out. Current tools were kept.')
    if code:
        # Keep potentially private paths/URLs in the local log, not the main status.
        raise RuntimeError('Tool validation/install failed (exit ' + str(code) + '). Current tools were kept. Log: ' + str(log))


def unpack_tool(archive, target, names):
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > 1024 * 1024 * 1024:
            raise ValueError('Tool archive expands beyond its limit')
        for name in names:
            matches = [i for i in z.infolist() if not i.is_dir() and Path(i.filename).name == name]
            if len(matches) != 1:
                raise ValueError('Tool archive is incomplete')
            dest = target / name
            with z.open(matches[0]) as source, dest.open('xb') as output:
                shutil.copyfileobj(source, output)
            with dest.open('rb') as source:
                if source.read(2) != b'MZ':
                    raise ValueError('Tool is not a Windows executable')
        licenses = target / 'licenses' / archive.stem
        licenses.mkdir(parents=True)
        for info in z.infolist():
            name = Path(info.filename).name
            if not info.is_dir() and info.file_size < 2 * 1024 * 1024 and any(s in name.lower() for s in ('license', 'copying', 'readme')):
                (licenses / name).write_bytes(z.read(info))


def stage(progress):
    """Resolve compatible wheels, pin hashes, install offline, and smoke-test."""
    if not WINDOWS:
        raise RuntimeError('Download-tool updates run in the installed Windows app.')
    directory = mdm_components.DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    bundle = directory / ('bundle-' + uuid.uuid4().hex)
    bundle.mkdir()
    packages, tool_dir = bundle / 'packages', bundle / 'tools'
    packages.mkdir(); tool_dir.mkdir()
    try:
        progress('Checking official tool releases…', .02)
        tools = [github_tool(label) for label in REPOSITORIES]
        current = inventory()
        active = mdm_components.selected()
        current_tools = active / 'tools' if active else BASE.parent / 'tools'
        def number(value):
            match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', value)
            return tuple(int(x or 0) for x in match.groups()) if match else (-1,)
        for item in tools:
            item['reuse'] = (number(current.get(item['label'], '')) >= number(item['version'])
                             and all((current_tools / name).is_file() for name in item['executables']))
            if item['reuse']:
                item['version'] = current[item['label']]
        # pip is bootstrapped into a temporary wheel, never installed system-wide.
        pip = read_json('https://pypi.org/pypi/pip/json')
        wheels = [a for a in pip['urls'] if a['filename'].endswith('-py3-none-any.whl') and not a.get('yanked')]
        if len(wheels) != 1:
            raise ValueError('No compatible pip bootstrap wheel')
        with tempfile.TemporaryDirectory(prefix='stage-', dir=directory) as tmp:
            tmp = Path(tmp)
            wheel = tmp / wheels[0]['filename']
            download(wheels[0]['url'], wheel, wheels[0]['digests']['sha256'], wheels[0]['size'], lambda n: None)
            pip_command = [worker_python(), '-X', 'utf8', '-c',
                           'import sys; sys.path.insert(0,sys.argv.pop(1)); from pip._internal.cli.main import main; sys.exit(main())',
                           str(wheel), '--isolated', '--disable-pip-version-check']
            report = tmp / 'report.json'
            log = directory / 'last-update.log'
            log.write_text('', encoding='utf-8')
            progress('Resolving compatible yt-dlp, EJS and Drive packages…', .08)
            wanted = []
            for name in ('yt-dlp', 'yt-dlp-ejs', 'gdown'):
                value = current[name]
                requirement = name + ('[default]' if name == 'yt-dlp' else '')
                if re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', value):
                    requirement += '>=' + value
                wanted.append(requirement)
            run_checked(pip_command + ['install', '--dry-run', '--ignore-installed', '--only-binary=:all:',
                        '--index-url', 'https://pypi.org/simple', '--report', str(report)] + wanted, log)
            resolved = json.loads(report.read_text(encoding='utf-8'))['install']
            if not resolved or len(resolved) > 100:
                raise ValueError('Unexpected package dependency plan')
            installed = {d.metadata.get('Name', '').lower().replace('_', '-'): d.version
                         for d in reversed(list(importlib.metadata.distributions()))}
            if all(x['reuse'] for x in tools) and all(installed.get(x['metadata']['name'].lower().replace('_', '-')) == x['metadata']['version'] for x in resolved):
                shutil.rmtree(bundle)
                return None
            requirements = []
            for item in resolved:
                url = item['download_info']['url']
                parsed = urllib.parse.urlsplit(url)
                digest = item['download_info']['archive_info']['hashes']['sha256']
                if parsed.hostname != 'files.pythonhosted.org' or not parsed.path.endswith('.whl') or not re.fullmatch('[a-f0-9]{64}', digest):
                    raise ValueError('Only hashed PyPI wheels can be installed')
                allowed_url(url)
                requirements.append(url + ' --hash=sha256:' + digest)
            requirements_file = tmp / 'requirements.txt'
            requirements_file.write_text('\n'.join(requirements) + '\n', encoding='utf-8')
            progress('Installing verified Python tool packages…', .18)
            run_checked(pip_command + ['install', '--no-index', '--no-deps', '--ignore-installed',
                        '--only-binary=:all:', '--require-hashes', '--no-compile', '--target', str(packages),
                        '-r', str(requirements_file)], log)
            for index, item in enumerate(tools):
                if item['reuse']:
                    for name in item['executables']:
                        shutil.copy2(current_tools / name, tool_dir / name)
                    if (current_tools / 'licenses').is_dir():
                        shutil.copytree(current_tools / 'licenses', tool_dir / 'licenses', dirs_exist_ok=True)
                    continue
                archive = tmp / (item['label'] + '.zip')
                download(item['url'], archive, item['sha256'], item['size'],
                         lambda n, i=index, x=item: progress('Downloading ' + x['label'] + ' ' + x['version'] + '…', .35 + i * .23 + n * .23))
                unpack_tool(archive, tool_dir, item['executables'])
            progress('Testing the new tools before activation…', .84)
            for name in ('deno', 'ffmpeg', 'ffprobe'):
                run_checked([str(tool_dir / (name + '.exe')), '--version' if name == 'deno' else '-version'], log, 30)
            # Force the staged packages to the front in an isolated worker.
            probe = ('import sys; sys.path.insert(0,sys.argv[1]); '
                     'import yt_dlp,yt_dlp_ejs,gdown; from mdm.mp4_engine import CompatibleMP4PP; '
                     'p=yt_dlp.parse_options(["--ignore-config","--skip-download","https://example.com/video"]); '
                     'd=yt_dlp.YoutubeDL(p.ydl_opts); d.add_post_processor(CompatibleMP4PP(d),when="post_process"); '
                     'print(yt_dlp.version.__version__)')
            run_checked([worker_python(), '-X', 'utf8', '-c', probe, str(packages)], log, 40)
            # Check the exact conversion codecs required by MDM, without network media.
            sample = tmp / 'probe.mp4'
            run_checked([str(tool_dir / 'ffmpeg.exe'), '-v', 'error', '-f', 'lavfi', '-i',
                         'color=c=black:s=160x90:r=10', '-f', 'lavfi', '-i', 'anullsrc', '-t', '0.2',
                         '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(sample)], log, 60)
            atomic_json(bundle / 'versions.json', {'tools': tools, 'packages': [
                {'name': x['metadata']['name'], 'version': x['metadata']['version']} for x in resolved]})
        return bundle
    except BaseException:
        shutil.rmtree(bundle, ignore_errors=True)
        raise


def activate_bundle(bundle):
    """One pointer commit switches all tools; keep the old bundle for rollback."""
    if bundle.parent != mdm_components.DIRECTORY or not (bundle / 'versions.json').is_file():
        raise ValueError('Unverified tool bundle')
    old = mdm_components.selected()
    atomic_json(mdm_components.DIRECTORY / 'current.json', {'bundle': bundle.name, 'previous': old.name if old else None})
    mdm_components.activate()
