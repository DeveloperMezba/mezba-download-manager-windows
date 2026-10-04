"""Installer-owned preparation, verified media-tool setup, registration, recovery."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
if sys.stdout is not None:sys.stdout.reconfigure(encoding='utf-8',errors='replace')
APP=Path(__file__).resolve().parent;ROOT=APP.parent
sys.path.insert(0,str(APP))
from mdm.common import STATE,init_state,atomic_json
from mdm.platform_support import filelocks,hidden_process
from mdm.service import _request


def stop_service():
    if not (STATE/'endpoint.json').exists():return {}
    try:restore=_request({'action':'prepare_update'},10)
    except (FileNotFoundError,ConnectionRefusedError):return {}
    deadline=time.monotonic()+35
    while not _request({'action':'update_ready'},5):
        if time.monotonic()>deadline:raise RuntimeError('A download is still stopping. Pause it and run the installer again.')
        time.sleep(.2)
    _request({'action':'shutdown'},5)
    with open(STATE/'service.lock','a+') as lock:
        while True:
            try:filelocks.flock(lock,filelocks.LOCK_EX|filelocks.LOCK_NB);filelocks.flock(lock,filelocks.LOCK_UN);break
            except BlockingIOError:
                if time.monotonic()>deadline:raise RuntimeError('The background service did not stop.')
                time.sleep(.2)
    return restore


def prepare():
    init_state()
    with open(STATE/'gui.lock','a+') as lock:
        deadline=time.monotonic()+15
        while True:
            try:filelocks.flock(lock,filelocks.LOCK_EX|filelocks.LOCK_NB);filelocks.flock(lock,filelocks.LOCK_UN);break
            except BlockingIOError:
                if time.monotonic()>deadline:raise RuntimeError('Close the MDM desktop window, then try the installer again.')
                time.sleep(.2)
    restore=stop_service()
    if restore or not (STATE/'update-resume.json').exists():atomic_json(STATE/'update-resume.json',restore)
    atomic_json(STATE/'installing.json',{'started':time.time()})


def get_file(url,path,expected,size):
    digest=hashlib.sha256();done=0;reported=0
    request=urllib.request.Request(url,headers={'User-Agent':'MezbaDownloadManager-Windows/0.1.0'})
    if not url.startswith('https://github.com/'):raise ValueError('Unexpected media-tool download host')
    with urllib.request.urlopen(request,timeout=90) as response,path.open('wb') as output:
        while True:
            block=response.read(256*1024)
            if not block:break
            done+=len(block)
            if done>size:raise ValueError('Media download exceeded its expected size')
            output.write(block);digest.update(block)
            if done-reported>=10*1024*1024:print(f'  Downloaded {done//1048576} / {size//1048576} MiB',flush=True);reported=done
    if done!=size or digest.hexdigest()!=expected:raise ValueError('Media-tool checksum failed. Please retry setup.')


def install_tools():
    tools=ROOT/'tools';tools.mkdir(exist_ok=True)
    for item in json.loads((APP/'media-tools-lock.json').read_text()):
        marker=tools/(item['name']+'.json')
        if marker.exists() and json.loads(marker.read_text()).get('sha256')==item['sha256'] and all((tools/name).is_file() for name in item['executables']):continue
        print('Downloading '+item['name']+' '+item['version']+' (verified SHA-256)…',flush=True)
        with tempfile.TemporaryDirectory(prefix='mdm-setup-',dir=ROOT) as temporary:
            archive=Path(temporary)/'tool.zip';get_file(item['url'],archive,item['sha256'],item['size'])
            with zipfile.ZipFile(archive) as z:
                if sum(i.file_size for i in z.infolist())>800*1024*1024:raise ValueError('Tool package expanded size is invalid')
                for name in item['executables']:
                    matches=[i for i in z.infolist() if Path(i.filename).name==name and not i.is_dir()]
                    if len(matches)!=1:raise ValueError('Tool archive is incomplete')
                    target=Path(temporary)/name
                    with z.open(matches[0]) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
                    if target.read_bytes()[:2]!=b'MZ':raise ValueError('Media tool is not a Windows executable')
                    os.replace(target,tools/name)
                licenses=tools/'licenses'/item['name'];licenses.mkdir(parents=True,exist_ok=True)
                for i in z.infolist():
                    if not i.is_dir() and i.file_size<2*1024*1024 and any(word in Path(i.filename).name.lower() for word in ('license','copying','readme')):
                        (licenses/Path(i.filename).name).write_bytes(z.read(i))
            atomic_json(marker,{'sha256':item['sha256'],'version':item['version'],'source':item['url']})


def register():
    import winreg
    directory=ROOT/'native-hosts';directory.mkdir(exist_ok=True)
    common={'name':'io.mezba.mdm','description':'Mezba Download Manager','path':str(ROOT/'MDMNativeHost.exe'),'type':'stdio'}
    ext_id=(APP/'extension/chromium-id.txt').read_text().strip()
    chromium=directory/'chromium.json';firefox=directory/'firefox.json'
    atomic_json(chromium,{**common,'allowed_origins':['chrome-extension://'+ext_id+'/']})
    atomic_json(firefox,{**common,'allowed_extensions':['mdm@mezba.local']})
    for branch in ('Google\\Chrome','Chromium','Microsoft\\Edge','BraveSoftware\\Brave-Browser','Vivaldi'):
        for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Software\\'+branch+'\\NativeMessagingHosts\\io.mezba.mdm',0,winreg.KEY_WRITE|view) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(chromium))
    for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Software\\Mozilla\\NativeMessagingHosts\\io.mezba.mdm',0,winreg.KEY_WRITE|view) as key:winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(firefox))


def health_and_restore():
    os.environ['PATH']=str(ROOT/'tools')+os.pathsep+os.environ.get('PATH','')
    for module in ('tkinter','yt_dlp','gdown'):
        if importlib.util.find_spec(module) is None:raise RuntimeError('Missing runtime module: '+module)
    for name in ('ffmpeg','ffprobe','deno'):
        subprocess.run([str(ROOT/'tools'/(name+'.exe')),'--version' if name=='deno' else '-version'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,**hidden_process())
    with open(STATE/'service.log','ab') as log:subprocess.Popen([sys.executable,str(APP/'mdm.py'),'--daemon'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,**hidden_process())
    from mdm import __version__
    deadline=time.monotonic()+15
    while True:
        try:
            if _request({'action':'ping'},2).get('version')!=__version__:raise RuntimeError('Unexpected download service version')
            break
        except (FileNotFoundError,ConnectionRefusedError):
            if time.monotonic()>deadline:raise RuntimeError('The download service could not start. See the service log.')
            time.sleep(.2)
    restore=json.loads((STATE/'update-resume.json').read_text()) if (STATE/'update-resume.json').exists() else {}
    _request({'action':'restore_after_update','restore':restore},5)
    (STATE/'update-resume.json').unlink(missing_ok=True);(STATE/'installing.json').unlink(missing_ok=True)


def unregister():
    stop_service()
    import winreg
    for branch in ('Google\\Chrome','Chromium','Microsoft\\Edge','BraveSoftware\\Brave-Browser','Vivaldi','Mozilla'):
        for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
            try:winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,'Software\\'+branch+'\\NativeMessagingHosts\\io.mezba.mdm',view,0)
            except FileNotFoundError:pass
    (STATE/'installing.json').unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','finish','recover','unregister']);args=parser.parse_args();init_state()
    if os.name=='nt':
        import csv,re
        identity=subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True,**hidden_process())
        sid=next(csv.reader(identity.strip().splitlines()))[-1]
        if not re.fullmatch(r'S-1-[0-9-]+',sid):raise RuntimeError('Could not identify the current Windows account')
        subprocess.run(['icacls',str(STATE),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F'],check=True,stdout=subprocess.DEVNULL,**hidden_process())
    if args.action=='prepare':prepare()
    elif args.action=='finish':install_tools();register();health_and_restore();print('MDM setup finished.',flush=True)
    elif args.action=='recover':health_and_restore()
    else:unregister()

if __name__=='__main__':
    try:main()
    except Exception as e:print('SETUP ERROR: '+str(e),flush=True);raise SystemExit(1)
