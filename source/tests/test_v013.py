"""0.1.3 regression tests: resilient startup, stall watchdog, GUI text helpers."""
import json, os, sys, tempfile, threading, time, unittest, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('MDM_STATE_DIR', tempfile.mkdtemp())
from mdm import media
from mdm.http_engine import DownloadError
from mdm.service import load_settings


class Settings(unittest.TestCase):
    def test_damaged_settings_never_stop_startup(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 's.json'
            p.write_text('{not json')
            self.assertEqual(load_settings(p)['concurrent'], 2)
            p.write_text(json.dumps({'concurrent': 99, 'retries': 'x', 'cookies_browser': 'evil', 'folder': 5}))
            s = load_settings(p)
            self.assertEqual((s['concurrent'], s['retries'], s['cookies_browser']), (4, 8, ''))
            self.assertIsInstance(s['folder'], str)


class Watchdog(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX supervisor used for the portable check')
    def test_silent_engine_is_reported_not_hung(self):
        task = {'kind': 'media', 'folder': tempfile.mkdtemp(), 'quality': 'best', 'url': 'https://example.org/v', 'filename': 'x'}
        old = (media.STARTUP_TIMEOUT, media.media_command, media.shutil.which)
        media.STARTUP_TIMEOUT = 1
        media.media_command = lambda t, s: [sys.executable, '-c', 'import time;time.sleep(60)']
        media.shutil.which = lambda name: '/bin/true'
        try:
            started = time.monotonic()
            with self.assertRaises(DownloadError) as ctx:
                media.run_external(task, {'speed_kib': 0}, threading.Event(), lambda *_: None)
            self.assertIn('no output', str(ctx.exception))
            self.assertLess(time.monotonic() - started, 30)
        finally:
            media.STARTUP_TIMEOUT, media.media_command, media.shutil.which = old


class GuiHelpers(unittest.TestCase):
    def setUp(self):
        try:
            from mdm import gui
        except ImportError:
            self.skipTest('tkinter unavailable')
        self.gui = gui

    def test_clock_and_detail(self):
        g = self.gui
        self.assertEqual((g.clock(45), g.clock(185), g.clock(7620)), ('45s', '3m 05s', '2h 07m'))
        t = {'status': 'downloading', 'done': 50, 'total': 100, 'speed': 10, 'quality': 'best', 'start_at': 0}
        self.assertIn('50%', g.detail_text(t))
        self.assertIn('5s left', g.detail_text(t))
        self.assertEqual(g.fraction(t), .5)
        self.assertIsNone(g.fraction({**t, 'total': None}))
        self.assertTrue(g.looks_like_video('https://www.youtube.com/watch?v=1'))
        self.assertFalse(g.looks_like_video('https://example.com/file.zip'))

    @unittest.skipUnless(shutil.which('xvfb-run') or os.environ.get('DISPLAY'), 'needs a display')
    def test_cards_update_in_place(self):
        import tkinter as tk
        g = self.gui
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        win = g.Window(root)
        now = time.time()
        task = dict(id='a' * 12, url='https://x.io/f', kind='file', quality='best', title='One', filename='f', folder='.',
                    status='downloading', done=1, total=10, speed=1, error='', created=now, start_at=now, sha256='', output='')
        win.tasks = [task]; win.render()
        card = win.cards[task['id']]; widget = card.title
        win.tasks = [{**task, 'done': 5}]; win.render()
        self.assertIs(win.cards[task['id']], card)
        self.assertIs(card.title, widget)
        win.tasks = [{**task, 'status': 'complete', 'done': 10}]; win.render()
        self.assertEqual(card.pill.cget('text'), 'COMPLETED')
        win.tasks = []; win.render()
        self.assertEqual(win.cards, {})
        root.destroy()


if __name__ == '__main__':
    unittest.main()
