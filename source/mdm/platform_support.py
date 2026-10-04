"""Small OS boundary: file locks, offsets, process trees and shell actions."""
import os
from pathlib import Path
import subprocess
import sys
import threading
WINDOWS = os.name == 'nt'

if WINDOWS:
    import msvcrt
    class FileLocks:
        LOCK_EX=1; LOCK_NB=4; LOCK_UN=8
        @staticmethod
        def flock(file, flags):
            file.seek(0)
            try:msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK if flags & 8 else msvcrt.LK_NBLCK, 1)
            except OSError as e:
                if flags & 8:raise
                raise BlockingIOError('Another MDM process holds this lock') from e
    filelocks = FileLocks()
else:
    import fcntl as filelocks

def sync_directory(path):
    if WINDOWS:return  # Windows file data is fsynced; POSIX directory fsync is unavailable.
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def pwrite(fd,data,offset,lock):
    if not WINDOWS:return os.pwrite(fd,data,offset)
    with lock:
        os.lseek(fd,offset,os.SEEK_SET)
        return os.write(fd,data)

def promote(source,target):
    if WINDOWS:os.rename(source,target)  # Windows rename fails if the destination exists.
    else:os.link(source,target);os.unlink(source)

def open_folder(path):
    Path(path).mkdir(parents=True,exist_ok=True)
    if WINDOWS:os.startfile(str(Path(path).resolve()))
    else:subprocess.Popen(['xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def hidden_process():
    return {'creationflags':subprocess.CREATE_NO_WINDOW} if WINDOWS else {}

def gui_python():
    candidate=Path(sys.executable).with_name('pythonw.exe')
    return str(candidate) if WINDOWS and candidate.exists() else sys.executable

def stop_process_tree(proc):
    if proc.poll() is not None:return
    if WINDOWS:
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**hidden_process())
    else:
        import signal
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass


def set_sparse(fd):
    if not WINDOWS:return True
    import ctypes,msvcrt
    from ctypes import wintypes as w
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.DeviceIoControl.argtypes=[w.HANDLE,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.c_void_p]
    k.DeviceIoControl.restype=w.BOOL
    returned=w.DWORD()
    return bool(k.DeviceIoControl(msvcrt.get_osfhandle(fd),0x000900c4,None,0,None,0,ctypes.byref(returned),None))


def worker_python():
    return str(Path(sys.executable).with_name('python.exe')) if WINDOWS else sys.executable


def spawn_background(command, **kwargs):
    """Keep the app/service independent of a short-lived browser native host.

    Break away only when the enclosing Windows job permits it. If it does not,
    retry ordinary creation without changing any OS/browser security policy.
    """
    if not WINDOWS:
        return subprocess.Popen(command, start_new_session=True, **kwargs)
    flags = 0x08000000  # CREATE_NO_WINDOW
    try:
        return subprocess.Popen(command, creationflags=flags | 0x01000000, **kwargs)
    except OSError as error:
        if getattr(error, 'winerror', None) != 5:
            raise
        return subprocess.Popen(command, creationflags=flags, **kwargs)
