"""Win32 media worker handles. Imported only by the standalone Windows supervisor."""
import ctypes
from ctypes import wintypes as w
import os
import subprocess
import sys


class Limits(ctypes.Structure):
    _fields_ = [('ProcessTime', ctypes.c_longlong), ('JobTime', ctypes.c_longlong),
                ('Flags', w.DWORD), ('MinWS', ctypes.c_size_t), ('MaxWS', ctypes.c_size_t),
                ('Active', w.DWORD), ('Affinity', ctypes.c_size_t),
                ('Priority', w.DWORD), ('Scheduling', w.DWORD)]


class IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
               ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]


class Extended(ctypes.Structure):
    _fields_ = [('Basic', Limits), ('IO', IO), ('ProcessMemory', ctypes.c_size_t),
                ('JobMemory', ctypes.c_size_t), ('PeakProcessMemory', ctypes.c_size_t),
                ('PeakJobMemory', ctypes.c_size_t)]


class WindowsWorker:
    def __init__(self):
        import _winapi
        self.win = _winapi
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'OpenProcess': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            'CreateJobObjectW': ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            'SetInformationJobObject': ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            'AssignProcessToJobObject': ([w.HANDLE, w.HANDLE], w.BOOL),
            'ResumeThread': ([w.HANDLE], w.DWORD),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.k, name)
            fn.argtypes, fn.restype = args, result

    def open_owner(self, pid):
        handle = self.k.OpenProcess(0x00100000, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def create_job(self):
        job = self.k.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.k.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close(job)
            raise error
        return job

    def create_suspended(self, command):
        import msvcrt
        # Supply valid stdin even when launched by pythonw.exe or a browser host.
        # Duplicate only stdio: the job and service handles must not be inherited.
        with open(os.devnull, 'rb') as null:
            duplicates = []
            try:
                for stream in (null, sys.stdout, sys.stderr):
                    fd = os.dup(stream.fileno())
                    duplicates.append(fd)
                    os.set_inheritable(fd, True)
                handles = [msvcrt.get_osfhandle(fd) for fd in duplicates]
                startup = subprocess.STARTUPINFO()
                startup.dwFlags = subprocess.STARTF_USESTDHANDLES
                startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
                startup.lpAttributeList = {'handle_list': handles}
                process, thread, _, _ = self.win.CreateProcess(
                    command[0], subprocess.list2cmdline(command), None, None, True,
                    0x00000004 | subprocess.CREATE_NO_WINDOW, None, None, startup)
                return process, thread
            finally:
                for fd in duplicates:
                    os.close(fd)

    def assign(self, job, process):
        if not self.k.AssignProcessToJobObject(job, process):
            code = ctypes.get_last_error()
            raise OSError(code, 'Windows could not supervise the download worker. '
                          'Open MDM from the Start menu, then retry from your browser. '
                          f'Windows error {code}.')

    def resume(self, thread):
        if self.k.ResumeThread(thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())

    def exited(self, handle, timeout):
        result = self.win.WaitForSingleObject(handle, timeout)
        if result == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 0

    def exit_code(self, process):
        return self.win.GetExitCodeProcess(process)

    def terminate_if_running(self, process):
        if not self.exited(process, 0):
            self.win.TerminateProcess(process, 1)
            self.win.WaitForSingleObject(process, 5000)

    def close(self, handle):
        self.win.CloseHandle(handle)
