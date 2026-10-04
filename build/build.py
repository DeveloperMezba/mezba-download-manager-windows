#!/usr/bin/env python3
"""Assemble the private runtime and compile real Windows PE launchers/installer.
Needs Python 3, a MinGW-w64 compiler (GCC + windres), NSIS, and msiextract on Linux.
On Windows, supply --tcltk-extracted from msiexec /a tcltk.msi TARGETDIR=... /qn.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[1]

def download(url,path,digest):
    if not path.exists():
        print('Downloading '+url,flush=True)
        with urllib.request.urlopen(url,timeout=120) as response,path.open('wb') as file:shutil.copyfileobj(response,file)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Checksum mismatch: '+str(path))

def run(command,**kwargs):
    print('Running '+str(command[0]),flush=True);subprocess.run([str(s) for s in command],check=True,**kwargs)

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,default=ROOT/'build-cache');p.add_argument('--cc',default='x86_64-w64-mingw32-gcc');p.add_argument('--windres',default='x86_64-w64-mingw32-windres');p.add_argument('--makensis',default='makensis');p.add_argument('--msiextract',default='msiextract');p.add_argument('--tcltk-extracted',type=Path);args=p.parse_args()
    cache=args.cache.resolve();cache.mkdir(parents=True,exist_ok=True)
    payload=ROOT/'dist/payload'
    if payload.exists():shutil.rmtree(payload)
    runtime=payload/'runtime';runtime.mkdir(parents=True)
    lock=json.loads((ROOT/'build/python-runtime-lock.json').read_text())
    for item in lock:download(item['url'],cache/item['name'],item['sha256'])
    with zipfile.ZipFile(cache/lock[0]['name']) as z:z.extractall(runtime)
    tcl=args.tcltk_extracted
    if not tcl:
        tcl=cache/'tcltk';tcl.mkdir(exist_ok=True)
        run([args.msiextract,'-C',tcl,cache/'tcltk.msi'])
    shutil.copytree(tcl/'Lib/tkinter',runtime/'Lib/tkinter',dirs_exist_ok=True)
    shutil.copytree(tcl/'tcl',runtime/'tcl',dirs_exist_ok=True)
    for file in (tcl/'DLLs').iterdir():
        if file.suffix.lower() in ('.dll','.pyd'):shutil.copy2(file,runtime/file.name)
    wheels=cache/'wheels';wheels.mkdir(exist_ok=True)
    for item in json.loads((ROOT/'build/python-packages-lock.json').read_text()):
        download(item['url'],wheels/item['name'],item['sha256'])
        with zipfile.ZipFile(wheels/item['name']) as z:z.extractall(runtime/'Lib/site-packages')
    # Explicit paths make the embeddable distribution work without system Python,
    # pip, PYTHONPATH, or the working directory being on sys.path.
    (runtime/'python313._pth').write_text('python313.zip\n.\nLib\nLib/site-packages\n../app\nimport site\n')
    shutil.copytree(ROOT/'source',payload/'app',ignore=shutil.ignore_patterns('__pycache__','*.pyc','tests'))
    for name in ('README.md','LICENSE'):shutil.copy2(ROOT/name,payload/name)
    shutil.copytree(ROOT/'third-party-source',payload/'app/third-party-source')
    (payload/'app/docs').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'docs/THIRD-PARTY.md',payload/'app/docs/THIRD-PARTY.md')
    build=ROOT/'build';obj=ROOT/'dist/launcher.o'
    run([args.windres,'launcher.rc','-O','coff','-o',obj],cwd=build)
    run([args.cc,'-municode','-mwindows','-Os','-s','-static','-o',payload/'MDM.exe',build/'launcher.c',obj,'-lshell32'])
    shutil.copy2(payload/'MDM.exe',payload/'MDMNativeHost.exe')
    version=(ROOT/'VERSION').read_text().strip()
    output=ROOT/'dist'/f'Mezba-Download-Manager-{version}-Windows-x64-Setup.exe'
    # POSIX NSIS accepts -D, Windows NSIS expects /D.
    prefix='/' if os.name=='nt' else '-'
    run([args.makensis,prefix+'V2',prefix+'DVERSION='+version,prefix+'DPAYLOAD='+str(payload),prefix+'DOUTPUT='+str(output),'installer.nsi'],cwd=build)
    if output.read_bytes()[:2]!=b'MZ':raise RuntimeError('Build did not produce a Windows executable')
    (ROOT/'dist/SHA256SUMS').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
    print('Built '+str(output)+' ('+str(output.stat().st_size)+' bytes)',flush=True)

if __name__=='__main__':main()
