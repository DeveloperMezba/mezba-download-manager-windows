"""Windows desktop UI using the private Python/Tk runtime, no browser engine.

0.1.3: new visual design, in-place list updates (no flicker or scroll jumps),
dialogs that size to their content and scale with Windows display scaling,
single-instance dialogs, keyboard shortcuts and a clearer progress window.
"""
import concurrent.futures
import json
import os
import queue
import re
import subprocess
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import urllib.parse
from . import __version__
from .common import BASE, STATE, human
from .service import request
from .platform_support import open_folder

# ── Palette ────────────────────────────────────────────────────────────────
BG = '#0b0f17'
SIDE = '#0f1520'
CARD = '#151c2a'
CARD2 = '#1b2436'
HOVER = '#232f47'
BORDER = '#25324a'
TEXT = '#e9eff9'
MUTED = '#93a3bd'
DIM = '#62728c'
MINT = '#5eead4'
MINT_HOVER = '#8ff3e2'
GREEN = '#4ade80'
AMBER = '#fbbf24'
BLUE = '#7aa7ff'
ERROR = '#ff8f85'
FONT = 'Segoe UI'

# status -> (short label, accent colour, pill background)
STATUS = {
    'downloading': ('Downloading', MINT, '#10332f'),
    'queued': ('Queued', BLUE, '#1a2a4d'),
    'paused': ('Paused', AMBER, '#3a2f10'),
    'pausing': ('Saving…', AMBER, '#3a2f10'),
    'verifying': ('Verifying', BLUE, '#1a2a4d'),
    'complete': ('Completed', GREEN, '#123522'),
    'error': ('Needs attention', ERROR, '#3d1c1a'),
}
BUSY = ('queued', 'downloading', 'pausing')
FILTERS = ('All downloads', 'Downloading', 'Queued', 'Paused', 'Complete', 'Error')
VIDEO_HOSTS = ('youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com', 'vimeo.com', 'twitter.com',
               'x.com', 'facebook.com', 'fb.watch', 'dailymotion.com', 'twitch.tv', 'soundcloud.com')
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)
SCALE = 1.0


def px(value):
    """Pixels that follow the Windows display-scaling factor (fonts already do)."""
    return int(value * SCALE)


def font(size=10, weight='normal'):
    return (FONT, size, weight)


# ── Text helpers (pure, unit-testable) ─────────────────────────────────────
def clock(seconds):
    """Human ETA: 45s, 3m 05s, 2h 07m."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f'{hours}h {minutes:02d}m'
    if minutes:
        return f'{minutes}m {secs:02d}s'
    return f'{secs}s'


def clip(text, limit=140):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def bucket(task):
    return 'paused' if task['status'] == 'pausing' else task['status']


def fraction(task):
    """0..1 when the total is known, 1 when complete, otherwise None."""
    if task['status'] == 'complete':
        return 1.0
    total = task.get('total') or 0
    return min(1.0, task['done'] / total) if total else None


def status_text(task):
    if task['status'] == 'downloading':
        if not task['done']:
            return 'Connecting / preparing download…'
        if task.get('total') and task['done'] >= task['total']:
            return 'Finishing / processing current file…'
    if task['status'] == 'queued' and task['start_at'] > time.time():
        return 'Scheduled for ' + time.strftime('%H:%M', time.localtime(task['start_at']))
    return {'complete': 'Completed', 'error': 'Needs attention', 'pausing': 'Saving progress…'}.get(
        task['status'], task['status'].capitalize())


def short_status(task):
    label_text = STATUS.get(task['status'], (task['status'].capitalize(), MUTED, CARD2))[0]
    if task['status'] == 'downloading' and not task['done']:
        return 'Preparing'
    if task['status'] == 'downloading' and task.get('total') and task['done'] >= task['total']:
        return 'Finishing'
    if task['status'] == 'queued' and task['start_at'] > time.time():
        return 'Scheduled ' + time.strftime('%H:%M', time.localtime(task['start_at']))
    return label_text


def status_color(task):
    return STATUS.get(task['status'], ('', MUTED, CARD2))[1]


def detail_text(task):
    done, total, speed = task['done'], task.get('total') or 0, task.get('speed') or 0
    if task['status'] == 'complete':
        text = human(total or done)
    else:
        text = human(done) + (' / ' + human(total) if total else '')
        if total:
            text += f' · {min(100, int(done * 100 / total))}%'
        if speed:
            text += ' · ' + human(speed) + '/s'
        if speed and total > done:
            text += ' · ' + clock((total - done) / speed) + ' left'
    if task['quality'].startswith('playlist:'):
        text = f"Item {task.get('playlist_index') or '?'}/{task.get('playlist_count') or '?'} · " + text
    return text


def looks_like_video(url):
    host = (urllib.parse.urlsplit(url.strip()).hostname or '').lower()
    return any(host == h or host.endswith('.' + h) for h in VIDEO_HOSTS)


def enable_dpi_awareness():
    """Crisp text on scaled Windows displays. Safe to call more than once."""
    if os.name != 'nt':
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Mezba.MDM')
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ── Widgets ────────────────────────────────────────────────────────────────
def label(parent, text, size=10, color=TEXT, weight='normal', **kwargs):
    return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color, font=font(size, weight),
                    anchor='w', justify='left', **kwargs)


def set_enabled(widget, enabled):
    widget.config(state='normal' if enabled else 'disabled', cursor='hand2' if enabled else 'arrow',
                  bg=widget._base if enabled else widget._off)


def button(parent, text, command, primary=False, small=False, kind=None):
    """kind: 'primary' | 'secondary' | 'ghost' | 'danger'. Hover and keyboard-focus states included."""
    kind = kind or ('primary' if primary else 'secondary')
    parent_bg = parent.cget('bg')
    base, hover, fg, off = {
        'primary': (MINT, MINT_HOVER, BG, CARD2),
        'secondary': (CARD2, HOVER, TEXT, parent_bg),
        'ghost': (parent_bg, HOVER, MUTED, parent_bg),
        'danger': (CARD2, '#4a2623', ERROR, parent_bg),
    }[kind]
    b = tk.Button(parent, text=text, command=command, bg=base, fg=fg, activebackground=hover,
                  activeforeground=fg if kind != 'ghost' else TEXT, disabledforeground=DIM,
                  relief='flat', bd=0, highlightthickness=2, highlightbackground=parent_bg,
                  highlightcolor=MINT, padx=10 if small else 16, pady=3 if small else 8,
                  cursor='hand2', font=font(9 if small else 10, 'bold' if kind == 'primary' else 'normal'),
                  takefocus=True)
    b._base, b._off = base, off

    def enter(_):
        if str(b['state']) != 'disabled':
            b.config(bg=hover)

    def leave(_):
        if str(b['state']) != 'disabled':
            b.config(bg=base)
    b.bind('<Enter>', enter)
    b.bind('<Leave>', leave)
    return b


class Field(tk.Entry):
    """Entry with an optional placeholder. Use .value() (never .get()) for the real text."""

    def __init__(self, parent, value='', placeholder=''):
        super().__init__(parent, bg=CARD2, fg=TEXT, insertbackground=MINT, relief='flat', bd=px(7), font=font(10),
                         highlightthickness=1, highlightbackground=BORDER, highlightcolor=MINT,
                         disabledbackground=CARD, disabledforeground=DIM,
                         selectbackground=MINT, selectforeground=BG)
        self.placeholder, self.showing = placeholder, False
        if value:
            self.insert(0, value)
        self.bind('<FocusIn>', lambda _: self._hide(), add='+')
        self.bind('<FocusOut>', lambda _: self._show(), add='+')
        self._show()

    def _show(self):
        if self.placeholder and not tk.Entry.get(self):
            self.showing = True
            self.config(fg=DIM)
            self.insert(0, self.placeholder)

    def _hide(self):
        if self.showing:
            self.showing = False
            self.delete(0, 'end')
            self.config(fg=TEXT)

    def value(self):
        return '' if self.showing else tk.Entry.get(self)

    def set(self, text):
        self._hide()
        self.delete(0, 'end')
        self.insert(0, text)
        if not text and self.focus_get() is not self:
            self._show()


def entry(parent, value='', placeholder=''):
    return Field(parent, value, placeholder)


class Bar(tk.Canvas):
    """Thin rounded progress bar with per-state colour and one shared indeterminate animation."""

    def __init__(self, parent, ui, height=6):
        self.thickness = px(height)
        super().__init__(parent, height=self.thickness, bg=parent.cget('bg'), highlightthickness=0, bd=0)
        self.ui = ui
        self.value, self.mode, self.color, self.phase = 0.0, 'determinate', MINT, 0.0
        self.bind('<Configure>', lambda _: self.draw())
        self.bind('<Destroy>', lambda _: ui.bars.discard(self))

    def set(self, value=None, color=MINT):
        mode = 'indeterminate' if value is None else 'determinate'
        value = 0.0 if value is None else max(0.0, min(1.0, value))
        if (mode, value, color) == (self.mode, self.value, self.color):
            return
        self.mode, self.value, self.color = mode, value, color
        (self.ui.bars.add if mode == 'indeterminate' else self.ui.bars.discard)(self)
        self.draw()

    def step(self):
        self.phase = (self.phase + 0.018) % 1.0
        self.draw()

    def draw(self):
        self.delete('all')
        width, r = self.winfo_width(), self.thickness / 2
        if width < self.thickness * 2:
            return
        self.create_line(r, r, width - r, r, width=self.thickness, capstyle='round', fill=BORDER)
        if self.mode == 'determinate' and self.value > 0:
            end = max(r + .1, r + (width - 2 * r) * self.value)
            self.create_line(r, r, end, r, width=self.thickness, capstyle='round', fill=self.color)
        elif self.mode == 'indeterminate':
            span = width * .32
            start = (width + span) * self.phase - span
            a, b = max(r, start), min(width - r, start + span)
            if b > a:
                self.create_line(a, r, b, r, width=self.thickness, capstyle='round', fill=self.color)


class Pill(tk.Label):
    def __init__(self, parent):
        super().__init__(parent, font=font(8, 'bold'), padx=9, pady=2)


class Nav(tk.Frame):
    """Sidebar filter row with an active indicator and a count."""

    def __init__(self, parent, text, command):
        super().__init__(parent, bg=SIDE, cursor='hand2', takefocus=True, highlightthickness=2,
                         highlightbackground=SIDE, highlightcolor=MINT)
        self.is_active = False
        self.mark = tk.Frame(self, bg=SIDE, width=3)
        self.mark.pack(side='left', fill='y')
        self.name = tk.Label(self, text=text, bg=SIDE, fg=MUTED, font=font(10), anchor='w', padx=12, pady=6)
        self.name.pack(side='left', fill='x', expand=True)
        self.count = tk.Label(self, text='', bg=SIDE, fg=DIM, font=font(9), padx=10)
        self.count.pack(side='right')
        for widget in (self, self.name, self.count):
            widget.bind('<Button-1>', lambda _: command())
            widget.bind('<Enter>', lambda _: self.paint(True))
            widget.bind('<Leave>', lambda _: self.paint(False))
        self.bind('<Return>', lambda _: command())
        self.bind('<space>', lambda _: command())

    def paint(self, hover=False):
        bg = CARD2 if self.is_active else HOVER if hover else SIDE
        for widget in (self, self.name, self.count):
            widget.config(bg=bg)
        self.config(highlightbackground=SIDE)
        self.mark.config(bg=MINT if self.is_active else bg)
        self.name.config(fg=TEXT if self.is_active else MUTED)
        self.count.config(fg=MINT if self.is_active else DIM)

    def active(self, flag):
        self.is_active = flag
        self.paint()


# ── Shared UI base ─────────────────────────────────────────────────────────
class UI:
    def __init__(self, root):
        global SCALE
        self.root = root
        try:
            SCALE = max(1.0, root.winfo_fpixels('1i') / 96)
        except tk.TclError:
            SCALE = 1.0
        self.events = queue.Queue()
        self.bars = set()
        self.dialogs = {}
        root.configure(bg=BG)
        root.option_add('*Font', font(10))
        root.option_add('*TCombobox*Listbox.background', CARD2)
        root.option_add('*TCombobox*Listbox.foreground', TEXT)
        root.option_add('*TCombobox*Listbox.selectBackground', MINT)
        root.option_add('*TCombobox*Listbox.selectForeground', BG)
        root.option_add('*TCombobox*Listbox.font', font(10))
        icon = BASE / 'assets' / 'mdm.ico'
        if os.name == 'nt' and icon.is_file():
            try:
                root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=TEXT, fieldbackground=CARD2)
        style.configure('TCombobox', fieldbackground=CARD2, background=CARD2, foreground=TEXT, arrowcolor=MINT,
                        bordercolor=BORDER, lightcolor=CARD2, darkcolor=CARD2, selectbackground=CARD2,
                        selectforeground=TEXT, padding=7, arrowsize=px(14))
        style.map('TCombobox', fieldbackground=[('readonly', CARD2)], foreground=[('readonly', TEXT)],
                  bordercolor=[('focus', MINT)], background=[('active', HOVER)])
        style.configure('Vertical.TScrollbar', background=BORDER, troughcolor=BG, bordercolor=BG,
                        arrowcolor=MUTED, lightcolor=BORDER, darkcolor=BORDER, gripcount=0, arrowsize=px(12))
        style.map('Vertical.TScrollbar', background=[('active', HOVER)])
        # Scrolling the page must never change a dropdown by accident.
        root.unbind_class('TCombobox', '<MouseWheel>')
        root.after(80, self.deliver)
        root.after(40, self.animate)

    def deliver(self):
        try:
            while True:
                callback, value = self.events.get_nowait()
                callback(value)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(80, self.deliver)

    def animate(self):
        for bar in list(self.bars):
            try:
                if bar.winfo_exists() and bar.winfo_ismapped():
                    bar.step()
            except tk.TclError:
                self.bars.discard(bar)
        if self.root.winfo_exists():
            self.root.after(40, self.animate)

    def work(self, fn, done, failed=None):
        future = POOL.submit(fn)

        def finished(f):
            try:
                value = f.result()
                callback = done
            except Exception as e:
                value = str(e)
                callback = failed or self.error
            self.events.put((callback, value))
        future.add_done_callback(finished)

    def call(self, message, done=lambda _: None, failed=None):
        self.work(lambda: request(message), done, failed)

    def error(self, error):
        messagebox.showerror('MDM', str(error), parent=self.root)

    # Dialogs size to their content, open centred, close with Esc and never stack.
    def focus_dialog(self, key):
        existing = self.dialogs.get(key)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return True
        return False

    def dialog(self, title, width=560, key=None, subtitle=''):
        d = tk.Toplevel(self.root)
        d.title('MDM · ' + title)
        d.configure(bg=BG, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        d.transient(self.root)
        d.minsize(px(width), px(120))
        if key:
            self.dialogs[key] = d
            d.bind('<Destroy>', lambda e, k=key: self.dialogs.pop(k, None) if e.widget is d else None)
        d.bind('<Escape>', lambda _: d.destroy())
        f = tk.Frame(d, bg=BG, padx=px(26), pady=px(22))
        f.pack(fill='both', expand=True)
        label(f, title, 18, weight='bold').pack(fill='x')
        if subtitle:
            label(f, subtitle, 10, MUTED, wraplength=px(width - 60)).pack(fill='x', pady=(3, 0))
        tk.Frame(f, bg=BG, height=px(14)).pack()
        return d, f

    def reveal(self, d, focus=None):
        """Centre over the main window once the content size is known."""
        d.update_idletasks()
        w, h = d.winfo_reqwidth(), d.winfo_reqheight()
        root = self.root
        x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - h) // 3)
        x = max(0, min(x, d.winfo_screenwidth() - w - 10))
        y = max(0, min(y, d.winfo_screenheight() - h - 60))
        d.geometry(f'+{x}+{y}')
        d.after(40, lambda: (d.focus_force(), focus.focus_set() if focus is not None else None))


def field_label(parent, text, first=False):
    label(parent, text, 8, MUTED, weight='bold').pack(fill='x', pady=(0 if first else 12, 4))


# ── Progress window ────────────────────────────────────────────────────────
class ProgressWindow:
    def __init__(self, ui, task_id, standalone=False):
        self.ui, self.task_id, self.task, self.busy = ui, task_id, None, False
        self.window = ui.root if standalone else tk.Toplevel(ui.root)
        self.window.title('MDM · Download progress')
        self.window.configure(bg=BG)
        self.window.minsize(px(480), px(300))
        if not standalone:
            self.window.transient(ui.root)
        f = tk.Frame(self.window, bg=BG, padx=px(26), pady=px(22))
        f.pack(fill='both', expand=True)
        top = tk.Frame(f, bg=BG)
        top.pack(fill='x')
        label(top, 'MDM', 12, MINT, 'bold').pack(side='left')
        label(top, '  DOWNLOAD PROGRESS', 8, DIM, 'bold').pack(side='left', pady=(3, 0))
        self.pill = Pill(top)
        self.pill.pack(side='right')
        self.title = label(f, 'Connecting to your download…', 15, weight='bold', wraplength=px(420))
        self.title.pack(fill='x', pady=(16, 6))
        self.status = label(f, 'Starting', 10, MINT, wraplength=px(420))
        self.status.pack(fill='x')
        self.bar = Bar(f, ui, 8)
        self.bar.pack(fill='x', pady=14)
        self.bar.set(None)
        self.detail = label(f, '', 10, MUTED, wraplength=px(420))
        self.detail.pack(fill='x')
        row = tk.Frame(f, bg=BG)
        row.pack(fill='x', pady=(18, 12))
        self.control = button(row, 'Pause', self.toggle, primary=True)
        self.control.pack(side='left', padx=(0, 8))
        button(row, 'Open folder', lambda: self.task and open_folder(self.task['folder'])).pack(side='left')
        self.note = label(f, 'Closing this window keeps the download running.', 9, DIM, wraplength=px(420))
        self.note.pack(fill='x', side='bottom')
        self.pill.config(text='CONNECTING', fg=MUTED, bg=CARD2)
        f.bind('<Configure>', self.relayout)
        if not standalone:
            self.window.bind('<Escape>', lambda _: self.window.destroy())
            ui.reveal(self.window)
        self.poll()

    def relayout(self, event):
        wrap = max(px(260), event.width - px(52))
        for widget in (self.title, self.status, self.detail, self.note):
            widget.config(wraplength=wrap)

    def poll(self):
        if not self.window.winfo_exists():
            return
        if not self.busy:
            self.busy = True

            def got(t):
                self.busy = False
                if not self.window.winfo_exists():
                    return
                self.task = t
                accent, tint = status_color(t), STATUS.get(t['status'], ('', MUTED, CARD2))[2]
                self.title.config(text=clip(t['title'], 220))
                self.status.config(text=status_text(t), fg=accent)
                self.detail.config(text=t.get('error') or detail_text(t), fg=ERROR if t.get('error') else MUTED)
                self.pill.config(text=short_status(t).upper(), fg=accent, bg=tint)
                value = fraction(t)
                self.bar.set(None if value is None and t['status'] in BUSY else value or 0, accent)
                pct = f'{int(value * 100)}% · ' if value is not None and t['status'] != 'complete' else ''
                self.window.title(pct + 'MDM · ' + clip(t['title'], 50))
                self.control.config(text='Pause' if t['status'] in ('queued', 'downloading')
                                    else 'Retry' if t['status'] == 'error' else 'Resume')
                set_enabled(self.control, t['status'] not in ('pausing', 'complete'))

            def fail(e):
                self.busy = False
                if self.window.winfo_exists() and not (self.task and self.task['status'] == 'complete'):
                    self.status.config(text=e[:170], fg=ERROR)
            self.ui.call({'action': 'get', 'id': self.task_id}, got, fail)
        self.window.after(1000, self.poll)

    def toggle(self):
        if self.task:
            running = self.task['status'] in ('queued', 'downloading')
            self.ui.call({'action': 'pause' if running else 'resume', 'id': self.task_id})


# ── A download card (updated in place, never rebuilt) ──────────────────────
class Card:
    def __init__(self, window, task):
        self.window, self.id, self.cache, self.has_error = window, task['id'], {}, False
        self.frame = tk.Frame(window.list_frame, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        self.stripe = tk.Frame(self.frame, bg=MUTED, width=4)
        self.stripe.pack(side='left', fill='y')
        body = tk.Frame(self.frame, bg=CARD, padx=px(18), pady=px(14))
        body.pack(side='left', fill='both', expand=True)
        head = tk.Frame(body, bg=CARD)
        head.pack(fill='x')
        self.pill = Pill(head)
        self.pill.pack(side='right', anchor='n', padx=(12, 0))
        self.title = label(head, '', 12, weight='bold', wraplength=window.wrap)
        self.title.pack(side='left', fill='x', expand=True)
        self.detail = label(body, '', 10, MUTED, wraplength=window.wrap + 90)
        self.detail.pack(fill='x', pady=(6, 9))
        self.bar = Bar(body, window, 6)
        self.bar.pack(fill='x')
        self.error = label(body, '', 9, ERROR, wraplength=window.wrap + 90)
        self.row = tk.Frame(body, bg=CARD)
        self.row.pack(fill='x', pady=(12, 0))
        self.primary = button(self.row, 'Pause', self.toggle, small=True)
        self.primary.pack(side='left', padx=(0, 6))
        self.folder_button = button(self.row, 'Folder', self.folder, small=True, kind='ghost')
        self.folder_button.pack(side='left', padx=(0, 2))
        button(self.row, 'Details', self.details, small=True, kind='ghost').pack(side='left', padx=(0, 2))
        button(self.row, 'Progress', self.progress, small=True, kind='ghost').pack(side='left')
        self.update(task)

    def put(self, name, widget, **options):
        if self.cache.get(name) != options:
            widget.config(**options)
            self.cache[name] = options

    def update(self, task):
        status = task['status']
        _, accent, tint = STATUS.get(status, (status, MUTED, CARD2))
        self.put('stripe', self.stripe, bg=accent)
        self.put('title', self.title, text=clip(task['title']))
        self.put('pill', self.pill, text=short_status(task).upper(), fg=accent, bg=tint)
        self.put('detail', self.detail, text=detail_text(task))
        value = fraction(task)
        self.bar.set(None if value is None and status in BUSY else value or 0, accent)
        error = (task.get('error') or '').strip()
        if error and status in ('error', 'paused'):
            first_line = error.splitlines()[0] if status == 'error' else error
            self.put('error', self.error, text=clip(first_line, 260))
            if not self.has_error:
                self.error.pack(fill='x', pady=(8, 0), before=self.row)
                self.has_error = True
        elif self.has_error:
            self.error.pack_forget()
            self.cache.pop('error', None)
            self.has_error = False
        if status == 'complete':
            self.primary.pack_forget()
        else:
            if not self.primary.winfo_manager():
                self.primary.pack(side='left', padx=(0, 6), before=self.folder_button)
            self.put('primary', self.primary,
                     text='Pause' if status in ('queued', 'downloading') else 'Retry' if status == 'error' else 'Resume')
            set_enabled(self.primary, status != 'pausing')

    def relayout(self, wrap):
        self.title.config(wraplength=wrap)
        self.detail.config(wraplength=wrap + 90)
        self.error.config(wraplength=wrap + 90)

    def current(self):
        return self.window.by_id.get(self.id)

    def toggle(self):
        task = self.current()
        if task:
            running = task['status'] in ('queued', 'downloading')
            self.window.call({'action': 'pause' if running else 'resume', 'id': self.id})

    def folder(self):
        task = self.current()
        if task:
            open_folder(task['folder'])

    def details(self):
        task = self.current()
        if task:
            self.window.details(task)

    def progress(self):
        ProgressWindow(self.window, self.id)


# ── Main window ────────────────────────────────────────────────────────────
class Window(UI):
    def __init__(self, root, updated=False):
        super().__init__(root)
        root.title('Mezba Download Manager')
        self.restore_geometry()
        root.minsize(px(860), px(560))
        self.tasks, self.by_id, self.settings = [], {}, {}
        self.polling = self.updating = False
        self.filter = FILTERS[0]
        self.cards, self.order, self.wrap = {}, [], 600
        self.build_sidebar()
        self.build_main()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Control-n>', lambda _: self.add_dialog())
        root.bind('<Control-f>', lambda _: (self.search.focus_set(), self.search.select_range(0, 'end')))
        root.bind('<Escape>', self.escape)
        self.poll()
        if updated:
            root.after(700, lambda: messagebox.showinfo(
                'MDM updated', 'Reload the browser extension and open video pages to use this version.', parent=root))

    # window state ---------------------------------------------------------
    def restore_geometry(self):
        self.root.geometry(f'{px(1120)}x{px(760)}')
        try:
            saved = json.loads((STATE / 'gui.json').read_text()).get('geometry', '')
            m = re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', saved)
            if not m:
                return
            w, h, x, y = map(int, m.groups())
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            w, h = max(px(860), min(w, sw)), max(px(560), min(h, sh))
            if 0 <= x <= sw - 200 and 0 <= y <= sh - 120:
                self.root.geometry(f'{w}x{h}+{x}+{y}')
            else:
                self.root.geometry(f'{w}x{h}')
        except (OSError, ValueError, tk.TclError):
            pass

    def close(self):
        try:
            if self.root.state() == 'normal':
                (STATE / 'gui.json').write_text(json.dumps({'geometry': self.root.geometry()}))
        except (OSError, tk.TclError):
            pass
        self.root.destroy()

    def bring_front(self):
        root = self.root
        root.deiconify()
        root.lift()
        root.attributes('-topmost', True)
        root.after(200, lambda: root.attributes('-topmost', False))
        root.focus_force()

    def escape(self, event):
        if event.widget is self.search:
            if self.search.value():
                self.search.set('')
                self.render()
            self.root.focus_set()

    # layout ----------------------------------------------------------------
    def build_sidebar(self):
        side = tk.Frame(self.root, bg=SIDE, width=px(240), padx=px(18), pady=px(24))
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        label(side, 'MDM', 30, MINT, 'bold').pack(fill='x')
        label(side, 'MEZBA DOWNLOAD MANAGER', 8, DIM, 'bold').pack(fill='x', pady=(0, 22))
        button(side, '+  New download', self.add_dialog, primary=True).pack(fill='x', pady=(0, 18))
        self.nav = {}
        for value in FILTERS:
            item = Nav(side, value, lambda v=value: self.set_filter(v))
            item.pack(fill='x', pady=1)
            self.nav[value] = item
        self.nav[self.filter].active(True)
        tk.Frame(side, bg=SIDE).pack(fill='y', expand=True)
        for text, command in (('Preferences', self.preferences), ('Browser setup', self.browser_setup), ('Update', self.updates)):
            b = button(side, text, command, kind='ghost')
            b.config(anchor='w', padx=px(14))
            b.pack(fill='x', pady=1)
        label(side, 'Windows ' + __version__, 9, DIM).pack(fill='x', pady=(16, 0))
        label(side, 'Small app. Big downloads.', 9, DIM).pack(fill='x')

    def build_main(self):
        main = tk.Frame(self.root, bg=BG, padx=px(28), pady=px(24))
        main.pack(side='left', fill='both', expand=True)
        head = tk.Frame(main, bg=BG)
        head.pack(fill='x')
        titles = tk.Frame(head, bg=BG)
        titles.pack(side='left')
        label(titles, 'Your downloads', 22, weight='bold').pack(fill='x')
        self.summary = label(titles, 'Connecting…', 10, MUTED)
        self.summary.pack(fill='x', pady=(2, 0))
        self.service = label(head, '● Connecting', 9, DIM)
        self.service.pack(side='right', anchor='n', pady=(8, 0))
        top = tk.Frame(main, bg=BG)
        top.pack(fill='x', pady=(20, 16))
        self.search = entry(top, placeholder='Search downloads…   (Ctrl+F)')
        self.search.pack(side='left', fill='x', expand=True, ipady=3)
        self.search.bind('<KeyRelease>', lambda _: self.render())
        button(top, 'Pause all', lambda: self.call({'action': 'pause_all'})).pack(side='right', padx=(10, 0))
        holder = tk.Frame(main, bg=BG)
        holder.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(holder, bg=BG, highlightthickness=0, yscrollincrement=px(36))
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True, padx=(0, 6))
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.embedded = self.canvas.create_window((0, 0), window=self.list_frame, anchor='nw')
        self.list_frame.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self.resize)
        self.empty = tk.Frame(self.list_frame, bg=BG)
        label(self.empty, 'Nothing here yet', 15, weight='bold').pack(pady=(px(60), 4))
        self.empty_hint = label(self.empty, '', 10, MUTED)
        self.empty_hint.pack()
        self.root.bind_all('<MouseWheel>', self.wheel)
        for key, amount, what in (('<Prior>', -1, 'pages'), ('<Next>', 1, 'pages'), ('<Up>', -1, 'units'), ('<Down>', 1, 'units')):
            self.root.bind(key, lambda e, a=amount, w=what: self.scroll_key(e, a, w))
        self.status = label(main, 'Connecting to the download service…', 9, DIM, wraplength=px(760))
        self.status.pack(fill='x', pady=(12, 0))

    def resize(self, event):
        self.canvas.itemconfigure(self.embedded, width=event.width)
        wrap = max(px(300), event.width - px(190))
        if abs(wrap - self.wrap) > px(24):
            self.wrap = wrap
            for card in self.cards.values():
                card.relayout(wrap)
            self.status.config(wraplength=event.width)

    def scrollable(self):
        return self.list_frame.winfo_height() > self.canvas.winfo_height()

    def wheel(self, event):
        if str(event.widget).startswith(str(self.canvas)) and self.scrollable():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    def scroll_key(self, event, amount, what):
        if isinstance(event.widget, (tk.Entry, ttk.Combobox, tk.Text)) or not self.scrollable():
            return
        self.canvas.yview_scroll(amount, what)

    # data ------------------------------------------------------------------
    def set_filter(self, value):
        self.filter = value
        for key, item in self.nav.items():
            item.active(key == value)
        self.render()
        self.canvas.yview_moveto(0)

    def poll(self):
        flag = STATE / 'raise.flag'
        if flag.exists():
            try:
                flag.unlink()
            except OSError:
                pass
            self.bring_front()
        if not self.updating and not self.polling:
            self.polling = True

            def got(result):
                self.polling = False
                self.tasks, self.settings = result['tasks'], result['settings']
                self.service.config(text='● Service running', fg=MINT)
                self.status.config(text='Downloads keep running when this window closes. Pause saves partial files.', fg=DIM)
                self.render()

            def fail(e):
                self.polling = False
                self.service.config(text='● Reconnecting…', fg=ERROR)
                self.status.config(text=e[:220], fg=ERROR)
            self.call({'action': 'list'}, got, fail)
        self.root.after(1200, self.poll)

    def match(self, task):
        return self.filter == FILTERS[0] or bucket(task) == self.filter.lower()

    def render(self):
        self.by_id = {t['id']: t for t in self.tasks}
        needle = self.search.value().strip().lower()
        counts = {name: 0 for name in FILTERS}
        counts[FILTERS[0]] = len(self.tasks)
        for t in self.tasks:
            name = bucket(t).capitalize()
            if name in counts:
                counts[name] += 1
        for name, item in self.nav.items():
            item.count.config(text=str(counts[name]) if counts[name] else '')
        active = counts['Downloading']
        self.summary.config(text=(f'{active} downloading · ' if active else '') + f'{len(self.tasks)} total')
        visible = [t for t in self.tasks if needle in t['title'].lower() and self.match(t)]
        ids = [t['id'] for t in visible]
        for stale in [i for i in self.cards if i not in ids]:
            self.cards.pop(stale).frame.destroy()
        created = False
        for t in visible:
            card = self.cards.get(t['id'])
            if card is None:
                self.cards[t['id']] = Card(self, t)
                created = True
            else:
                card.update(t)
        if created or ids != self.order:
            for card in self.cards.values():
                card.frame.pack_forget()
            for i in ids:
                self.cards[i].frame.pack(fill='x', pady=(0, 12))
        self.order = ids
        if visible:
            self.empty.pack_forget()
        else:
            if needle:
                hint = 'No downloads match your search.'
            elif self.filter == FILTERS[0]:
                hint = 'Add a link with  + New download  or use the MDM browser button.'
            else:
                hint = 'No downloads in this view.'
            self.empty_hint.config(text=hint)
            self.empty.pack(fill='x')

    # dialogs ---------------------------------------------------------------
    def clipboard_url(self):
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            return ''
        return text if re.fullmatch(r'https?://\S{4,2000}', text) else ''

    def add_dialog(self):
        if self.focus_dialog('add'):
            return
        d, f = self.dialog('New download', 620, 'add',
                           'Paste a video page, playlist, direct file or public Google Drive link.')
        field_label(f, 'LINK', True)
        url = entry(f, self.clipboard_url())
        url.pack(fill='x', ipady=3)
        field_label(f, 'TYPE')
        kind = ttk.Combobox(f, state='readonly', values=['Direct file / Google Drive', 'Video / audio'], height=2)
        kind.current(0)
        kind.pack(fill='x')
        touched = {'kind': False}
        defaults = [{'id': 'best', 'label': 'MKV · Best available video + audio'},
                    {'id': 'mp4:best', 'label': 'MP4 · Best available video + audio (H.264/AAC)'},
                    {'id': 'audio', 'label': 'Audio only · original quality'},
                    {'id': 'mp3', 'label': 'Audio only · MP3'}]
        selected = {'choices': defaults, 'url': '', 'tried': ''}

        media = tk.Frame(f, bg=BG)
        field_label(media, 'QUALITY / FORMAT')
        inspect_button = button(media, 'Find download options', lambda: inspect())
        inspect_button.pack(fill='x', pady=(0, 8))
        quality = ttk.Combobox(media, state='readonly', values=[c['label'] for c in defaults], height=12)
        quality.current(0)
        quality.pack(fill='x')

        files = tk.Frame(f, bg=BG)
        field_label(files, 'OPTIONAL FILENAME')
        filename = entry(files)
        filename.pack(fill='x', ipady=2)
        field_label(files, 'OPTIONAL SHA-256 (DIRECT FILES)')
        sha = entry(files)
        sha.pack(fill='x', ipady=2)

        schedule = tk.Frame(f, bg=BG)
        schedule.pack(fill='x')
        field_label(schedule, 'START AFTER (MINUTES, 0 = NOW)')
        delay = entry(schedule, '0')
        delay.pack(fill='x', ipady=2)
        status = label(f, '', 10, MUTED, wraplength=px(560))
        status.pack(fill='x', pady=(14, 0))
        actions = tk.Frame(f, bg=BG)
        actions.pack(fill='x', pady=(16, 0))
        add_button = button(actions, 'Download', lambda: add(), primary=True)
        add_button.pack(side='right')
        button(actions, 'Cancel', d.destroy, kind='ghost').pack(side='right', padx=(0, 8))

        def say(text, color=MUTED):
            if d.winfo_exists():
                status.config(text=text, fg=color)

        def show_mode():
            if kind.current() == 1:
                files.pack_forget()
                media.pack(fill='x', before=schedule)
                if not selected['tried']:
                    say('Press “Find download options” to see qualities and playlists, or download the best quality right away.')
            else:
                media.pack_forget()
                files.pack(fill='x', before=schedule)
                say('')

        def chosen(_):
            touched['kind'] = True
            show_mode()
        kind.bind('<<ComboboxSelected>>', chosen)

        def guess(_=None):
            if not touched['kind']:
                want = 1 if looks_like_video(url.value()) else 0
                if kind.current() != want:
                    kind.current(want)
                    show_mode()
        url.bind('<KeyRelease>', guess)

        def inspect():
            target = url.value().strip()
            if not target:
                say('Paste a link first.', ERROR)
                return
            selected['tried'] = target
            say('Inspecting video and playlist…')
            set_enabled(inspect_button, False)

            def got(info):
                if not d.winfo_exists():
                    return
                set_enabled(inspect_button, True)
                if url.value().strip() != target:
                    say('The link changed. Inspect it again.', AMBER)
                    return
                selected.update(choices=info['choices'], url=target)
                quality.config(values=[c['label'] for c in info['choices']])
                quality.current(0)
                kind.current(1)
                say(info.get('warning') or info['title'], AMBER if info.get('warning') else MINT)

            def failed(e):
                if d.winfo_exists():
                    set_enabled(inspect_button, True)
                    say(e[:250], ERROR)
            self.call({'action': 'analyze', 'url': target}, got, failed)

        def add():
            if str(add_button['state']) == 'disabled':
                return
            target = url.value().strip()
            if not target:
                say('Paste a link first.', ERROR)
                return
            try:
                minutes = int(delay.value().strip() or '0')
                if minutes < 0:
                    raise ValueError
            except ValueError:
                say('Enter a whole number of minutes (0 or more).', ERROR)
                return
            if selected['url'] and selected['url'] != target:
                say('The link changed. Inspect it again before choosing a format.', AMBER)
                return
            video = kind.current() == 1
            choice = selected['choices'][max(0, quality.current())] if video else {}
            message = {'action': 'add', 'kind': 'media' if video else 'file', 'url': choice.get('url', target),
                       'quality': choice.get('id', 'best'), 'title': choice.get('title', ''),
                       'filename': filename.value(), 'sha256': sha.value(), 'delay_minutes': minutes}
            set_enabled(add_button, False)
            say('Adding download and opening progress…')

            def got(task):
                if d.winfo_exists():
                    d.destroy()
                ProgressWindow(self, task['id'])

            def failed(e):
                if d.winfo_exists():
                    say(e[:250], ERROR)
                    set_enabled(add_button, True)
            self.call(message, got, failed)

        def enter(_):
            if kind.current() == 1 and selected['tried'] != url.value().strip() and url.value().strip():
                inspect()
            else:
                add()
        url.bind('<Return>', enter)
        delay.bind('<Return>', lambda _: add())
        guess()
        show_mode()
        self.reveal(d, url)

    def details(self, task):
        key = 'details-' + task['id']
        if self.focus_dialog(key):
            return
        d, f = self.dialog('Download details', 640, key)
        box = tk.Frame(f, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        box.pack(fill='both', expand=True)
        text = tk.Text(box, bg=CARD, fg=TEXT, relief='flat', height=10, wrap='word', padx=14, pady=12,
                       font=font(10), highlightthickness=0, insertbackground=MINT,
                       selectbackground=MINT, selectforeground=BG)
        text.pack(fill='both', expand=True)
        text.insert('1.0', task['title'] + '\n\nFormat: ' + task['quality'] + '\nFolder: ' + task['folder']
                    + ('\n\n' + task['error'] if task.get('error') else ''))
        text.config(state='disabled')
        field_label(f, 'LINK')
        replacement = entry(f, task['url'])
        replacement.pack(fill='x', ipady=3)
        if task['kind'] != 'file':
            replacement.config(state='disabled')
        row = tk.Frame(f, bg=BG)
        row.pack(fill='x', pady=(14, 0))

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(task['url'])
            copy_button.config(text='Copied ✓')
        copy_button = button(row, 'Copy link', copy)
        copy_button.pack(side='left', padx=(0, 8))
        if task['kind'] == 'file':
            button(row, 'Replace expired link (pause first)',
                   lambda: self.call({'action': 'replace_url', 'id': task['id'], 'url': replacement.value()},
                                     lambda _: d.destroy())).pack(side='left')

        def remove():
            if messagebox.askyesno('Remove history', 'Remove this task from the list? Downloaded files are kept.', parent=d):
                self.call({'action': 'remove', 'id': task['id']}, lambda _: d.destroy())
        button(row, 'Remove from history', remove, kind='danger').pack(side='right')
        self.reveal(d)

    def preferences(self):
        if self.focus_dialog('prefs'):
            return
        d, f = self.dialog('Preferences', 580, 'prefs')
        fields = {}
        first = True
        for name, title in [('folder', 'DOWNLOAD FOLDER'), ('concurrent', 'SIMULTANEOUS DOWNLOADS (1–4)'),
                            ('connections', 'CONNECTIONS PER FILE (1–8)'),
                            ('speed_kib', 'SPEED LIMIT PER TASK, KIB/S (0 = UNLIMITED)'),
                            ('retries', 'RETRY ATTEMPTS (0–30)')]:
            field_label(f, title, first)
            first = False
            e = entry(f, str(self.settings.get(name, '')))
            e.pack(fill='x', ipady=2)
            e.bind('<Return>', lambda _: save())
            fields[name] = e

        def browse():
            folder = filedialog.askdirectory(parent=d, initialdir=fields['folder'].value() or None)
            if folder:
                fields['folder'].set(os.path.normpath(folder))
        button(f, 'Choose folder…', browse, kind='ghost', small=True).pack(anchor='w', pady=(4, 0))
        field_label(f, 'SIGNED-IN BROWSER SESSION (OPTIONAL)')
        cookies = ttk.Combobox(f, state='readonly', values=['Off', 'firefox', 'chrome', 'chromium', 'brave', 'edge', 'vivaldi'])
        cookies.set(self.settings.get('cookies_browser') or 'Off')
        cookies.pack(fill='x')
        status = label(f, '', 10, ERROR, wraplength=px(520))
        status.pack(fill='x', pady=(12, 0))

        def save():
            try:
                values = {k: (v.value().strip() if k == 'folder' else int(v.value())) for k, v in fields.items()}
            except ValueError:
                status.config(text='Enter whole numbers for the limits.')
                return
            values['cookies_browser'] = '' if cookies.get() == 'Off' else cookies.get()
            self.call({'action': 'settings', 'settings': values}, lambda _: d.destroy(),
                      lambda e: status.config(text=e[:250]))

        def stop():
            if messagebox.askyesno('Stop MDM', 'Stop the background service and close MDM?\n\nActive downloads are paused and saved.', parent=d):
                self.call({'action': 'shutdown'}, lambda _: self.root.destroy())
        actions = tk.Frame(f, bg=BG)
        actions.pack(fill='x', pady=(18, 0))
        button(actions, 'Save preferences', save, primary=True).pack(side='right')
        button(actions, 'Cancel', d.destroy, kind='ghost').pack(side='right', padx=(0, 8))
        button(actions, 'Stop background service', stop, kind='danger').pack(side='left')
        self.reveal(d, fields['folder'])

    def browser_setup(self):
        if self.focus_dialog('browser'):
            return
        d, f = self.dialog('Browser setup', 600, 'browser', 'The installer registers the native host for your Windows account.')
        for title, body, text, path in (
                ('Chrome · Edge · Brave · Chromium',
                 'Open Extensions → turn on Developer mode → Load unpacked. Select the chromium folder, then reload existing video pages.',
                 'Open Chromium extension folder', BASE / 'extension/chromium'),
                ('Firefox',
                 'Open about:debugging → This Firefox → Load Temporary Add-on and choose firefox/manifest.json. This unsigned preview needs reloading after a Firefox restart.',
                 'Open Firefox extension folder', BASE / 'extension/firefox')):
            card = tk.Frame(f, bg=CARD, padx=px(18), pady=px(16), highlightthickness=1, highlightbackground=BORDER)
            card.pack(fill='x', pady=(0, 12))
            label(card, title, 13, weight='bold').pack(fill='x')
            label(card, body, 10, MUTED, wraplength=px(500)).pack(fill='x', pady=(6, 12))
            row = tk.Frame(card, bg=CARD)
            row.pack(fill='x')
            button(row, text, lambda p=path: open_folder(p), primary=True).pack(side='left')

            def copy(p=path):
                self.root.clipboard_clear()
                self.root.clipboard_append(str(p))
            button(row, 'Copy path', copy, kind='ghost').pack(side='left', padx=(8, 0))
        self.reveal(d)

    def updates(self):
        from . import updater
        if self.focus_dialog('updates'):
            return
        d, f = self.dialog('Update MDM', 650, 'updates', 'App and download tools update separately.')
        app = tk.Frame(f, bg=CARD, padx=px(18), pady=px(16), highlightthickness=1, highlightbackground=BORDER)
        app.pack(fill='x', pady=(0, 12))
        label(app, 'App update', 14, weight='bold').pack(fill='x')
        label(app, 'Windows ' + __version__ + '  ·  Your GitHub releases', 10, MUTED).pack(fill='x', pady=5)
        label(app, updater.get_repository() or 'Add your GitHub owner/repository in App update.', 10, MUTED,
              wraplength=px(570)).pack(fill='x')
        app_button = button(app, 'Open app update', self.app_updates)
        app_button.pack(anchor='w', pady=(12, 0))
        tools = tk.Frame(f, bg=CARD, padx=px(18), pady=px(16), highlightthickness=1, highlightbackground=BORDER)
        tools.pack(fill='both', expand=True)
        label(tools, 'Download tools', 14, weight='bold').pack(fill='x')
        versions = label(tools, 'Reading installed versions…', 10, MUTED, wraplength=px(570))
        versions.pack(fill='x', pady=7)
        label(tools, 'yt-dlp, EJS, Deno, FFmpeg / ffprobe and Google Drive support.', 10, DIM, wraplength=px(570)).pack(fill='x')
        state = label(tools, '', 10, MINT, wraplength=px(570))
        state.pack(fill='x', pady=8)
        bar = Bar(tools, self, 6)
        bar.pack(fill='x')

        def got_versions(data):
            if d.winfo_exists():
                lines = ['yt-dlp ' + data.get('yt-dlp', '?') + '  ·  EJS ' + data.get('yt-dlp-ejs', '?') + '  ·  Drive ' + data.get('gdown', '?'),
                         data.get('Deno', '?') + '  ·  ' + data.get('FFmpeg', '?')]
                versions.config(text='\n'.join(lines))

        def load_versions():
            self.call({'action': 'tools_versions'}, got_versions, lambda e: None)

        def start():
            set_enabled(update_button, False)
            state.config(text='Starting tool update…', fg=MINT)

            def failed(e):
                if d.winfo_exists():
                    set_enabled(update_button, True)
                    state.config(text=e[:400], fg=ERROR)
            self.call({'action': 'tools_update'}, lambda _: None, failed)
        update_button = button(tools, 'Check & update tools', start, primary=True)
        update_button.pack(anchor='w', pady=(14, 0))
        was_busy = {'value': False}

        def poll():
            if not d.winfo_exists():
                return

            def got(data):
                if not d.winfo_exists():
                    return
                busy = data['busy']
                set_enabled(update_button, not busy)
                set_enabled(app_button, not busy)
                state.config(text=(data.get('error') or data.get('message') or 'Updates use official sources. Downloads resume after switching tools.')[:450],
                             fg=ERROR if data.get('error') else MINT)
                bar.set(data.get('progress', 0), ERROR if data.get('error') else MINT)
                if was_busy['value'] and not busy:
                    load_versions()
                was_busy['value'] = busy
                d.after(1200, poll)

            def failed(e):
                if d.winfo_exists():
                    state.config(text=e[:300], fg=ERROR)
                    d.after(2000, poll)
            self.call({'action': 'tools_status'}, got, failed)
        load_versions()
        poll()
        self.reveal(d)

    def app_updates(self):
        from . import updater
        if self.focus_dialog('app-update'):
            return
        d, f = self.dialog('Check for updates', 600, 'app-update', 'Trusted public GitHub repository: owner/repository')
        repo = entry(f, updater.get_repository())
        repo.pack(fill='x', ipady=3)
        label(f, 'A newer Windows release will download and install when you check. Downloads pause, then MDM restarts.',
              10, MUTED, wraplength=px(540)).pack(fill='x', pady=(14, 0))
        status = label(f, '', 10, MINT, wraplength=px(540))
        status.pack(fill='x', pady=12)
        bar = Bar(f, self, 6)
        bar.pack(fill='x')

        def begin():
            self.updating = True
            set_enabled(start, False)
            repo.config(state='disabled')
            d.protocol('WM_DELETE_WINDOW', lambda: None)

            def progress(text, value):
                self.events.put((lambda pair: (status.config(text=pair[0], fg=MINT), bar.set(pair[1], MINT)), (text, value)))

            def done(result):
                self.updating = False
                if result.get('installer'):
                    subprocess.Popen([result['installer'], '/UPDATE'], close_fds=True)
                    self.root.destroy()
                else:
                    status.config(text='You already have the latest Windows version.', fg=MINT)
                    reset()

            def reset():
                self.updating = False
                set_enabled(start, True)
                repo.config(state='normal')
                d.protocol('WM_DELETE_WINDOW', d.destroy)

            def fail(e):
                status.config(text=e[:350], fg=ERROR)
                reset()
            value = repo.value()
            self.work(lambda: updater.check_and_download(value, progress), done, fail)
        start = button(f, 'Check & install update', begin, primary=True)
        start.pack(fill='x', pady=(18, 0))
        repo.bind('<Return>', lambda _: begin())
        self.reveal(d, repo)


def run(updated=False):
    from .common import init_state
    from .platform_support import filelocks
    init_state()
    with open(STATE / 'gui.lock', 'a+') as lock:
        try:
            filelocks.flock(lock, filelocks.LOCK_EX | filelocks.LOCK_NB)
        except BlockingIOError:
            # MDM is already open: ask that window to come to the front instead of silently doing nothing.
            try:
                (STATE / 'raise.flag').write_text(str(time.time()))
            except OSError:
                pass
            return 0
        enable_dpi_awareness()
        root = tk.Tk()
        Window(root, updated)
        root.mainloop()
        return 0
