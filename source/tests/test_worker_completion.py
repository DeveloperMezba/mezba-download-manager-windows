"""Completion/containment regressions; real Win32 cases run on Windows CI."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mdm.child import supervise_windows
from mdm import platform_support, media


class FakeWorker:
    def __init__(self, code=0, failed_assignment=False, parent_dies=False):
        self.events = []
        self.code = code
        self.failed_assignment = failed_assignment
        self.parent_dies = parent_dies
    def open_owner(self, pid): return 'owner'
    def create_job(self): return 'job'
    def create_suspended(self, command):
        self.events.append('suspended')
        return 'engine', 'thread'
    def assign(self, job, process):
        assert (job, process) == ('job', 'engine')
        self.events.append('assigned')
        if self.failed_assignment: raise OSError('assignment failed')
    def resume(self, thread): self.events.append('resumed')
    def exited(self, handle, timeout):
        if handle == 'owner': return self.parent_dies and timeout == 200
        return not self.parent_dies
    def exit_code(self, process): return self.code
    def terminate_if_running(self, process): self.events.append('cleanup-engine')
    def close(self, handle): self.events.append('closed-' + handle)


class WorkerRegressions(unittest.TestCase):
    def test_success_and_real_failure_codes_survive_cleanup(self):
        for code in (0, 1, 7):
            api = FakeWorker(code)
            self.assertEqual(supervise_windows(api, 123, ['engine']), code)
            self.assertEqual(api.events[:3], ['suspended', 'assigned', 'resumed'])
            self.assertEqual(api.events.count('closed-thread'), 1)
            for name in ('job', 'engine', 'owner'):
                self.assertIn('closed-' + name, api.events)
    def test_assignment_failure_never_runs_engine_and_closes_every_handle(self):
        api = FakeWorker(failed_assignment=True)
        with self.assertRaisesRegex(OSError, 'assignment failed'):
            supervise_windows(api, 123, ['engine'])
        self.assertNotIn('resumed', api.events)
        self.assertIn('cleanup-engine', api.events)
        for name in ('job', 'thread', 'engine', 'owner'):
            self.assertIn('closed-' + name, api.events)
    def test_owner_death_is_failure_and_cleans_job(self):
        api = FakeWorker(parent_dies=True)
        self.assertEqual(supervise_windows(api, 123, ['engine']), 1)
        self.assertIn('closed-job', api.events)
    def test_background_launch_requests_permitted_job_breakaway(self):
        with patch.object(platform_support, 'WINDOWS', True), patch.object(platform_support.subprocess, 'Popen') as popen:
            platform_support.spawn_background(['python.exe'])
            self.assertEqual(popen.call_args.kwargs['creationflags'], 0x09000000)
    def test_disallowed_breakaway_retries_normal_launch_only(self):
        error = OSError('Access denied'); error.winerror = 5
        with patch.object(platform_support, 'WINDOWS', True), patch.object(platform_support.subprocess, 'Popen', side_effect=[error, 'process']) as popen:
            self.assertEqual(platform_support.spawn_background(['python.exe']), 'process')
            self.assertEqual(popen.call_args.kwargs['creationflags'], 0x08000000)
        with patch.object(platform_support, 'WINDOWS', True), patch.object(platform_support.subprocess, 'Popen', side_effect=FileNotFoundError('missing')) as popen:
            with self.assertRaises(FileNotFoundError): platform_support.spawn_background(['missing'])
            self.assertEqual(popen.call_count, 1)
    def test_error_guidance_keeps_original_evidence(self):
        detail = 'ERROR: Could not copy Chrome cookie database.'
        self.assertIn(detail, media.engine_error(detail, 1))
        self.assertIn('Off and retry', media.engine_error(detail, 1))
        self.assertIn('exit code 7', media.engine_error('MDM_FILE final.mp4', 7))


@unittest.skipUnless(os.name == 'nt', 'Requires actual Windows Job Objects')
class WindowsWorkerIntegration(unittest.TestCase):
    def environment(self):
        return {**os.environ, 'PYTHONPATH': str(ROOT) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    def command(self, owner, script):
        return [sys.executable, '-X', 'utf8', str(ROOT/'mdm/child.py'), str(owner),
                sys.executable, '-X', 'utf8', '-c', script]
    def test_success_unicode_output_and_spaces(self):
        result = subprocess.run(self.command(os.getpid(), "print('MDM_FILE café music.mp4')"),
                                capture_output=True, encoding='utf-8', timeout=15, env=self.environment())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('café music.mp4', result.stdout)
    def test_engine_failure_is_preserved(self):
        result = subprocess.run(self.command(os.getpid(), 'raise SystemExit(7)'),
                                capture_output=True, timeout=15, env=self.environment())
        self.assertEqual(result.returncode, 7, result.stderr)
    def test_service_death_stops_engine_and_descendant(self):
        from mdm.windows_worker import WindowsWorker
        api = WindowsWorker()
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp)/'ready.json'
            # The owner represents the service. The engine launches a grandchild.
            engine = ("import subprocess,sys,time,os,json; from pathlib import Path; "
                      "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
                      f"Path({str(ready)!r}).write_text(json.dumps([os.getpid(),p.pid])); time.sleep(120)")
            owner_script = ("import subprocess,os,time; "
                            f"cmd={self.command(0, engine)!r}; cmd[4]=str(os.getpid()); "
                            "p=subprocess.Popen(cmd); time.sleep(120)")
            owner = subprocess.Popen([sys.executable, '-c', owner_script], env=self.environment(),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            handles = []
            try:
                deadline = time.monotonic() + 15
                while not ready.exists() and time.monotonic() < deadline: time.sleep(.05)
                self.assertTrue(ready.exists(), 'Worker did not start')
                import json
                handles = [api.open_owner(pid) for pid in json.loads(ready.read_text())]
                owner.kill(); owner.wait(timeout=5)
                for handle in handles:
                    self.assertTrue(api.exited(handle, 10000), 'Orphaned media process')
            finally:
                if owner.poll() is None: owner.kill(); owner.wait(timeout=5)
                for handle in handles: api.close(handle)


if __name__ == '__main__': unittest.main()
