"""Manual GitHub Windows release checks; launch the verified Windows installer."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request
from . import __version__
from .common import BASE,STATE,atomic_json,init_state

MAX_INSTALLER=250*1024*1024

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'v?(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})',value):raise ValueError('Use a stable Windows release version, such as v0.1.1.')
    return tuple(map(int,value.lstrip('v').split('.')))

def repository(value):
    value=value.strip().removeprefix('https://github.com/').rstrip('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}',value) or value.split('/')[-1] in ('.','..'):raise ValueError('Enter a trusted public GitHub repository as owner/repository.')
    return value

def get_repository():
    for file in (STATE/'update-source.json',BASE/'update-source.json'):
        if file.is_file():
            value=json.loads(file.read_text()).get('repository','')
            if value:return repository(value)
    return ''

class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urllib.parse.urlsplit(newurl);host=p.hostname or ''
        if p.scheme!='https' or p.username or not (host in ('github.com','api.github.com') or host.endswith('.githubusercontent.com')):raise ValueError('Unexpected update download redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_url(url):
    if urllib.parse.urlsplit(url).hostname not in ('api.github.com','github.com') or not url.startswith('https://'):raise ValueError('Updates must come from GitHub over HTTPS')
    return urllib.request.build_opener(Redirects()).open(urllib.request.Request(url,headers={'User-Agent':'MDM-Windows/'+__version__}),timeout=40)

def read(url,limit):
    with open_url(url) as r:data=r.read(limit+1)
    if len(data)>limit:raise ValueError('Update metadata is too large')
    return data

def check_and_download(repo,progress):
    repo=repository(repo);init_state();atomic_json(STATE/'update-source.json',{'repository':repo})
    progress('Checking '+repo+'…',.02)
    data=json.loads(read('https://api.github.com/repos/'+repo+'/releases/latest',2*1024*1024))
    tag=data.get('tag_name','');new=version(tag)
    if tag.lstrip('v') in ('1.0.0', '1.1.0'):
        raise ValueError('This repository still marks a legacy-numbered build as latest. Publish v0.1.2 or newer in the corrected Windows series and mark it as the latest release.')
    if data.get('draft') or data.get('prerelease') or new<=version(__version__):return {'updated':False}
    number='.'.join(map(str,new));name='Mezba-Download-Manager-'+number+'-Windows-x64-Setup.exe'
    def asset(filename):
        matches=[a for a in data.get('assets',[]) if a.get('name')==filename]
        if len(matches)!=1:raise ValueError('This release needs the Windows Setup.exe and SHA256SUMS assets. See the publishing guide.')
        result=matches[0];p=urllib.parse.urlsplit(result['browser_download_url'])
        if p.scheme!='https' or p.netloc!='github.com' or urllib.parse.unquote(p.path).lower()!=f'/{repo}/releases/download/{tag}/{filename}'.lower() or p.query or p.fragment:raise ValueError('Update asset belongs to a different repository/tag')
        return result
    installer=asset(name);sums=asset('SHA256SUMS');size=installer.get('size',0)
    if not isinstance(size,int) or not 0<size<=MAX_INSTALLER:raise ValueError('Invalid installer size')
    expected=[]
    for line in read(sums['browser_download_url'],65536).decode().splitlines():
        match=re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?(.+)',line.strip())
        if match and match[2]==name:expected.append(match[1].lower())
    if len(expected)!=1:raise ValueError('Installer checksum is missing or ambiguous')
    if installer.get('digest') and installer['digest']!='sha256:'+expected[0]:raise ValueError('GitHub and publisher checksums disagree')
    directory=Path(tempfile.mkdtemp(prefix='update-',dir=STATE));path=directory/name;digest=hashlib.sha256();done=0
    try:
        with open_url(installer['browser_download_url']) as response,path.open('xb') as file:
            while True:
                chunk=response.read(256*1024)
                if not chunk:break
                done+=len(chunk)
                if done>size:raise ValueError('Installer exceeds announced size')
                file.write(chunk);digest.update(chunk);progress('Downloading Windows '+number,.1+.85*done/size)
        if done!=size or digest.hexdigest()!=expected[0]:raise ValueError('Installer verification failed. Nothing was installed.')
        with path.open('rb') as file:
            if file.read(2)!=b'MZ':raise ValueError('The update is not a Windows executable')
        progress('Installer verified. Restarting MDM…',1)
        return {'updated':True,'installer':str(path)}
    except BaseException:
        path.unlink(missing_ok=True);directory.rmdir();raise
