"""Supervise media workers; Windows Job Objects contain all descendants."""
import ctypes
import os
import signal
import subprocess
import sys
import time


def windows(parent, command):
    """Only the engine belongs to the kill-on-close job, never this supervisor.

    Start suspended so it cannot spawn FFmpeg before containment is established.
    Preserve its real exit code after closing the job and all owned handles.
    """
    if not __package__:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mdm.windows_worker import WindowsWorker
    return supervise_windows(WindowsWorker(), parent, command)


def supervise_windows(api, parent, command):
    owner = job = process = thread = None
    try:
        owner = api.open_owner(parent)
        if api.exited(owner, 0):
            return 1
        job = api.create_job()
        process, thread = api.create_suspended(command)
        api.assign(job, process)
        api.resume(thread)
        api.close(thread)
        thread = None
        while not api.exited(process, 0):
            if api.exited(owner, 200):
                return 1
        return api.exit_code(process)
    finally:
        # Also terminate an unassigned suspended process if assignment failed.
        try:
            if process is not None:
                api.terminate_if_running(process)
        finally:
            for handle in (job, thread, process, owner):
                if handle is not None:
                    api.close(handle)


def posix(parent,command):
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGTERM,0,0,0):raise OSError(ctypes.get_errno(),'Could not supervise download engine')
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    if os.getppid()!=parent:return 1
    proc=subprocess.Popen(command)
    while proc.poll() is None:
        if stopping:
            signal.signal(signal.SIGINT,signal.SIG_IGN);os.killpg(os.getpgrp(),signal.SIGINT)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(os.getpgrp(),signal.SIGKILL)
            break
        time.sleep(.2)
    return proc.returncode if proc.returncode is not None and proc.returncode>=0 else 1

if __name__=='__main__':
    raise SystemExit((windows if os.name=='nt' else posix)(int(sys.argv[1]),sys.argv[2:]))
