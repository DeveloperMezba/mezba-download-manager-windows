"""Windows desktop UI using the private Python/Tk runtime, no browser engine."""
import concurrent.futures
import json
from pathlib import Path
import queue
import subprocess
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from . import __version__
from .common import BASE, STATE, human
from .service import request
from .platform_support import open_folder

BG='#10151f';CARD='#182231';TEXT='#eaf0fb';MUTED='#91a4bf';MINT='#70e0c2';BORDER='#293a50'
ERROR='#ffb6ae'
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=4)

class UI:
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.root.configure(bg=BG)
        self.root.option_add('*Font',('Segoe UI',10))
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',background=BG,foreground=TEXT,fieldbackground=CARD)
        style.configure('TCombobox',fieldbackground=CARD,background=BORDER,foreground=TEXT,arrowcolor=MINT)
        style.map('TCombobox',fieldbackground=[('readonly',CARD)],foreground=[('readonly',TEXT)])
        style.configure('Horizontal.TProgressbar',troughcolor=BORDER,background=MINT,bordercolor=CARD,lightcolor=MINT,darkcolor=MINT,borderwidth=0,thickness=7)
        style.configure('Vertical.TScrollbar',background=BORDER,troughcolor=BG,bordercolor=BG,arrowcolor=MUTED)
        self.root.after(80,self.deliver)
    def deliver(self):
        try:
            while True:
                callback,value=self.events.get_nowait();callback(value)
        except queue.Empty:pass
        if self.root.winfo_exists():self.root.after(80,self.deliver)
    def work(self,fn,done,failed=None):
        future=POOL.submit(fn)
        def finished(f):
            try:value=f.result();callback=done
            except Exception as e:value=str(e);callback=failed or self.error
            self.events.put((callback,value))
        future.add_done_callback(finished)
    def call(self,message,done=lambda _:None,failed=None):self.work(lambda:request(message),done,failed)
    def error(self,error):messagebox.showerror('MDM',str(error),parent=self.root)

def label(parent,text,size=10,color=TEXT,**kwargs):
    return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,font=('Segoe UI',size),anchor='w',**kwargs)

def button(parent,text,command,primary=False):
    return tk.Button(parent,text=text,command=command,bg=MINT if primary else BORDER,fg=BG if primary else TEXT,
                     activebackground=MINT,activeforeground=BG,relief='flat',bd=0,highlightthickness=1,highlightbackground=BORDER,highlightcolor=MINT,padx=12,pady=8,cursor='hand2')

def entry(parent,value=''):
    e=tk.Entry(parent,bg=CARD,fg=TEXT,insertbackground=MINT,relief='flat',highlightthickness=1,highlightbackground=BORDER)
    e.insert(0,value);return e

def dialog(root,title,width=590):
    d=tk.Toplevel(root);d.title('MDM · '+title);d.configure(bg=BG);d.geometry(str(width)+'x560');d.minsize(430,330)
    d.transient(root)
    f=tk.Frame(d,bg=BG,padx=22,pady=20);f.pack(fill='both',expand=True)
    label(f,title,19).pack(fill='x',pady=(0,16))
    return d,f

def status_text(task):
    if task['status']=='downloading':
        if not task['done']:return 'Connecting / preparing download…'
        if task.get('total') and task['done']>=task['total']:return 'Finishing / processing current file…'
    if task['status']=='queued' and task['start_at']>time.time():return 'Scheduled for '+time.strftime('%H:%M',time.localtime(task['start_at']))
    return {'complete':'Completed','error':'Needs attention','pausing':'Saving progress…'}.get(task['status'],task['status'].capitalize())

def status_color(task):
    return ERROR if task['status']=='error' else MINT if task['status'] in ('complete','downloading') else MUTED

def detail_text(task):
    done,total,speed=task['done'],task.get('total') or 0,task.get('speed') or 0
    text=human(done)+(' / '+human(total) if total else '')+(' · '+human(speed)+'/s' if speed else '')
    if speed and total>done:text+=' · '+str(round((total-done)/speed))+'s left'
    if task['quality'].startswith('playlist:'):text=f"Item {task.get('playlist_index') or '?'}/{task.get('playlist_count') or '?'} · "+text
    return text

class ProgressWindow:
    def __init__(self,ui,task_id,standalone=False):
        self.ui=ui;self.task_id=task_id;self.task=None;self.busy=False
        self.window=ui.root if standalone else tk.Toplevel(ui.root)
        self.window.title('MDM · Download progress');self.window.configure(bg=BG);self.window.geometry('475x325')
        f=tk.Frame(self.window,bg=BG,padx=22,pady=20);f.pack(fill='both',expand=True)
        label(f,'MDM  /  DOWNLOAD PROGRESS',11,MINT).pack(fill='x')
        self.title=label(f,'Connecting to your download…',16,wraplength=420);self.title.pack(fill='x',pady=14)
        self.status=label(f,'Starting',11,MINT,wraplength=420);self.status.pack(fill='x')
        self.bar=ttk.Progressbar(f,maximum=1);self.bar.pack(fill='x',pady=12)
        self.detail=label(f,'',10,MUTED,wraplength=420);self.detail.pack(fill='x')
        row=tk.Frame(f,bg=BG);row.pack(fill='x',pady=15)
        self.control=button(row,'Pause',self.toggle);self.control.pack(side='left',padx=(0,8))
        button(row,'Open folder',lambda:self.task and open_folder(self.task['folder'])).pack(side='left')
        label(f,'Closing this window keeps the download running.',9,MUTED,wraplength=420).pack(fill='x')
        self.poll()
    def poll(self):
        if not self.window.winfo_exists():return
        if not self.busy:
            self.busy=True
            def got(t):
                self.busy=False
                if not self.window.winfo_exists():return
                self.task=t;self.title.config(text=t['title']);self.status.config(text=status_text(t),fg=status_color(t));self.detail.config(text=t.get('error') or detail_text(t))
                self.bar.stop();self.bar.configure(mode='determinate')
                if t['status']=='complete':self.bar['value']=1
                elif t.get('total'):self.bar['value']=min(1,t['done']/t['total'])
                elif t['status'] in ('queued','downloading','pausing'):self.bar.configure(mode='indeterminate');self.bar.start(30)
                else:self.bar['value']=0
                self.control.config(text='Pause' if t['status'] in ('queued','downloading') else 'Retry' if t['status']=='error' else 'Resume',state='disabled' if t['status'] in ('complete','pausing') else 'normal')
            def fail(e):
                self.busy=False
                if self.window.winfo_exists() and not (self.task and self.task['status']=='complete'):self.status.config(text=e[:170])
            self.ui.call({'action':'get','id':self.task_id},got,fail)
        self.window.after(1200,self.poll)
    def toggle(self):
        if self.task:self.ui.call({'action':'pause' if self.task['status'] in ('queued','downloading') else 'resume','id':self.task_id})

class Window(UI):
    def __init__(self,root,updated=False):
        super().__init__(root);root.title('Mezba Download Manager');root.geometry('1080x730');root.minsize(800,520)
        self.tasks=[];self.settings={};self.polling=False;self.updating=False;self.filter='All downloads'
        side=tk.Frame(root,bg=CARD,width=215,padx=20,pady=25);side.pack(side='left',fill='y');side.pack_propagate(False)
        label(side,'MDM',34,MINT).pack(fill='x');label(side,'MEZBA\nDOWNLOAD MANAGER',10,MUTED).pack(fill='x',pady=(0,24))
        button(side,'+ New download',self.add_dialog,True).pack(fill='x',pady=(0,20))
        self.filter_buttons={}
        for value in ('All downloads','Downloading','Queued','Paused','Complete','Error'):
            b=button(side,value,lambda v=value:self.set_filter(v));b.pack(fill='x',pady=3);self.filter_buttons[value]=b
        self.filter_buttons['All downloads'].config(bg=MINT,fg=BG)
        tk.Frame(side,bg=CARD).pack(fill='y',expand=True)
        button(side,'Preferences',self.preferences).pack(fill='x',pady=4)
        button(side,'Browser setup',self.browser_setup).pack(fill='x',pady=4)
        button(side,'Update',self.updates).pack(fill='x',pady=4)
        label(side,'Windows '+__version__+'\nSmall app. Big downloads.',9,MUTED).pack(fill='x',pady=(18,0))
        main=tk.Frame(root,bg=BG,padx=24,pady=22);main.pack(side='left',fill='both',expand=True)
        label(main,'Your downloads.',25).pack(fill='x');label(main,'Video, audio and files. One place to keep them.',10,MUTED).pack(fill='x',pady=(4,20))
        top=tk.Frame(main,bg=BG);top.pack(fill='x',pady=(0,16));self.search=entry(top);self.search.pack(side='left',fill='x',expand=True,ipady=9)
        self.search.bind('<KeyRelease>',lambda _:self.render());button(top,'Pause all',lambda:self.call({'action':'pause_all'})).pack(side='right',padx=(10,0))
        holder=tk.Frame(main,bg=BG);holder.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(holder,bg=BG,highlightthickness=0);scroll=ttk.Scrollbar(holder,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.cards=tk.Frame(self.canvas,bg=BG);self.embedded=self.canvas.create_window((0,0),window=self.cards,anchor='nw')
        self.cards.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.embedded,width=e.width))
        root.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120),'units') if root.focus_get() is not self.search else None)
        root.bind('<Down>',lambda _:self.canvas.yview_scroll(1,'units') if root.focus_get() is not self.search else None)
        root.bind('<Up>',lambda _:self.canvas.yview_scroll(-1,'units') if root.focus_get() is not self.search else None)
        self.status=label(main,'Connecting to the download service…',9,MUTED,wraplength=740);self.status.pack(fill='x',pady=(12,0))
        self.poll()
        if updated:root.after(700,lambda:messagebox.showinfo('MDM updated','Reload the browser extension and open video pages to use this version.',parent=root))
    def set_filter(self,value):
        self.filter=value
        for key,b in self.filter_buttons.items():b.config(bg=MINT if key==value else BORDER,fg=BG if key==value else TEXT)
        self.render()
    def poll(self):
        if not self.updating and not self.polling:
            self.polling=True
            def got(result):
                self.polling=False;self.tasks=result['tasks'];self.settings=result['settings'];self.render();self.status.config(text='Downloads keep running when this window closes. Pause saves partial files.')
            def fail(e):self.polling=False;self.status.config(text=e[:220])
            self.call({'action':'list'},got,fail)
        self.root.after(1200,self.poll)
    def render(self):
        position=self.canvas.yview()[0]
        for child in self.cards.winfo_children():child.destroy()
        needle=self.search.get().lower();shown=0
        for task in self.tasks:
            if needle not in task['title'].lower() or (self.filter!='All downloads' and task['status']!=self.filter.lower()):continue
            shown+=1;card=tk.Frame(self.cards,bg=CARD,padx=16,pady=13,highlightthickness=1,highlightbackground=BORDER);card.pack(fill='x',pady=(0,10))
            label(card,task['title'],13,wraplength=660).pack(fill='x')
            label(card,status_text(task)+' · '+detail_text(task),10,status_color(task),wraplength=660).pack(fill='x',pady=7)
            bar=ttk.Progressbar(card,maximum=1);bar.pack(fill='x',pady=(0,10));bar['value']=1 if task['status']=='complete' else min(1,task['done']/task['total']) if task.get('total') else 0
            row=tk.Frame(card,bg=CARD);row.pack(fill='x')
            if task['status']!='complete':
                action='pause' if task['status'] in ('queued','downloading') else 'resume'
                b=button(row,'Pause' if action=='pause' else 'Retry' if task['status']=='error' else 'Resume',lambda i=task['id'],a=action:self.call({'action':a,'id':i}));b.pack(side='left',padx=(0,8))
                if task['status']=='pausing':b.config(state='disabled')
            button(row,'Folder',lambda p=task['folder']:open_folder(p)).pack(side='left',padx=(0,8))
            button(row,'Details',lambda t=task:self.details(t)).pack(side='left',padx=(0,8))
            button(row,'Progress',lambda i=task['id']:ProgressWindow(self,i)).pack(side='left')
        if not shown:label(self.cards,'No downloads here yet.\nAdd a link or use the MDM browser button.',14,MUTED,pady=40).pack(fill='x')
        self.cards.update_idletasks();self.canvas.yview_moveto(position)
    def add_dialog(self):
        d,f=dialog(self.root,'New download');d.geometry('640x640')
        label(f,'Video page, playlist, direct file or public Drive link').pack(fill='x');url=entry(f);url.pack(fill='x',ipady=8,pady=6)
        kind=ttk.Combobox(f,state='readonly',values=['Direct file / Google Drive','Video / audio'],height=2);kind.current(0);kind.pack(fill='x',pady=6)
        defaults=[{'id':'best','label':'MKV · Best available video + audio'},{'id':'mp4:best','label':'MP4 · Best available video + audio (H.264/AAC)'},{'id':'audio','label':'Audio only · original quality'},{'id':'mp3','label':'Audio only · MP3'}]
        selected={'choices':defaults,'url':''};quality=ttk.Combobox(f,state='readonly',values=[c['label'] for c in defaults],height=12);quality.current(0)
        status=label(f,'Inspect the video to discover qualities and playlists.',10,MUTED,wraplength=580)
        def inspect():
            target=url.get().strip();status.config(text='Inspecting video and playlist…');inspect_button.config(state='disabled')
            def got(info):
                if not d.winfo_exists():return
                inspect_button.config(state='normal')
                if url.get().strip()!=target:status.config(text='The link changed. Inspect it again.');return
                selected.update(choices=info['choices'],url=target);quality.config(values=[c['label'] for c in info['choices']]);quality.current(0);kind.current(1);status.config(text=info.get('warning') or info['title'])
            def failed(e):
                if d.winfo_exists():inspect_button.config(state='normal');status.config(text=e[:250])
            self.call({'action':'analyze','url':target},got,failed)
        inspect_button=button(f,'Find download options',inspect);inspect_button.pack(fill='x',pady=8);quality.pack(fill='x',pady=6)
        fields={}
        for name,title in [('filename','Optional filename (direct files / Drive)'),('sha256','Optional SHA-256 (direct files)'),('delay_minutes','Start after this many minutes (0 = now)')]:
            label(f,title,9,MUTED).pack(fill='x',pady=(8,3));e=entry(f,'0' if name=='delay_minutes' else '');e.pack(fill='x',ipady=6);fields[name]=e
        status.pack(fill='x',pady=10)
        def add():
            try:delay=int(fields['delay_minutes'].get())
            except ValueError:status.config(text='Enter a whole number of minutes.');return
            if selected['url'] and selected['url']!=url.get().strip():status.config(text='The link changed. Inspect it again before choosing a format.');return
            choice=selected['choices'][max(0,quality.current())] if kind.current()==1 else {}
            message={'action':'add','kind':'media' if kind.current()==1 else 'file','url':choice.get('url',url.get().strip()),'quality':choice.get('id','best'),'title':choice.get('title',''),'filename':fields['filename'].get(),'sha256':fields['sha256'].get(),'delay_minutes':delay}
            add_button.config(state='disabled');status.config(text='Adding download and opening progress…')
            def got(task):
                if d.winfo_exists():d.destroy()
                ProgressWindow(self,task['id'])
            def failed(e):
                if d.winfo_exists():status.config(text=e[:250]);add_button.config(state='normal')
            self.call(message,got,failed)
        add_button=button(f,'Download',add,True);add_button.pack(fill='x')
    def details(self,task):
        d,f=dialog(self.root,'Download details');d.geometry('650x480')
        text=tk.Text(f,bg=CARD,fg=TEXT,relief='flat',height=10,wrap='word');text.pack(fill='both',expand=True)
        text.insert('1.0',task['title']+'\n\nFormat: '+task['quality']+'\nFolder: '+task['folder']+'\n\n'+task.get('error',''));text.config(state='disabled')
        replacement=entry(f,task['url']);replacement.pack(fill='x',ipady=7,pady=10)
        if task['kind']=='file':button(f,'Replace expired link (pause first)',lambda:self.call({'action':'replace_url','id':task['id'],'url':replacement.get()},lambda _:d.destroy())).pack(fill='x',pady=4)
        def remove():
            if messagebox.askyesno('Remove history','Remove this task from the list? Downloaded files are kept.',parent=d):self.call({'action':'remove','id':task['id']},lambda _:d.destroy())
        button(f,'Remove from history',remove).pack(fill='x',pady=4)
    def preferences(self):
        d,f=dialog(self.root,'Preferences');fields={}
        for name,title in [('folder','Download folder'),('concurrent','Simultaneous downloads (1–4)'),('connections','Connections per file (1–8)'),('speed_kib','Speed limit per task, KiB/s (0 = unlimited)'),('retries','Retry attempts (0–30)')]:
            label(f,title,10,MUTED).pack(fill='x',pady=(6,3));e=entry(f,str(self.settings.get(name,'')));e.pack(fill='x',ipady=6);fields[name]=e
        def browse():
            folder=filedialog.askdirectory(parent=d)
            if folder:fields['folder'].delete(0,'end');fields['folder'].insert(0,folder)
        button(f,'Choose folder',browse).pack(fill='x',pady=6)
        label(f,'Signed-in browser session (optional)',10,MUTED).pack(fill='x');cookies=ttk.Combobox(f,state='readonly',values=['Off','firefox','chrome','chromium','brave','edge','vivaldi']);cookies.set(self.settings.get('cookies_browser') or 'Off');cookies.pack(fill='x',pady=6)
        def save():
            try:values={k:(v.get() if k=='folder' else int(v.get())) for k,v in fields.items()}
            except ValueError:self.error('Enter whole numbers for limits.');return
            values['cookies_browser']='' if cookies.get()=='Off' else cookies.get();self.call({'action':'settings','settings':values},lambda _:d.destroy())
        button(f,'Save preferences',save,True).pack(fill='x',pady=8)
        button(f,'Stop background service',lambda:self.call({'action':'shutdown'},lambda _:self.root.destroy())).pack(fill='x')
    def browser_setup(self):
        d,f=dialog(self.root,'Browser setup');d.geometry('620x465')
        label(f,'Chrome / Edge / Brave / Chromium',14).pack(fill='x')
        label(f,'Open Extensions → turn on Developer mode → Load unpacked. Select the chromium folder opened below. Reload existing video pages.',11,MUTED,wraplength=560,justify='left').pack(fill='x',pady=12)
        button(f,'Open Chromium extension folder',lambda:open_folder(BASE/'extension/chromium')).pack(fill='x')
        label(f,'Firefox',14).pack(fill='x',pady=(20,6))
        label(f,'Open about:debugging → This Firefox → Load Temporary Add-on. Choose firefox/manifest.json. This unsigned preview needs reloading after a Firefox restart.',11,MUTED,wraplength=560,justify='left').pack(fill='x',pady=10)
        button(f,'Open Firefox extension folder',lambda:open_folder(BASE/'extension/firefox')).pack(fill='x')
        label(f,'The installer registers the native host for your Windows account.',9,MUTED,wraplength=560).pack(fill='x',pady=16)
    def updates(self):
        from . import updater
        if getattr(self,'update_window',None) is not None and self.update_window.winfo_exists():
            self.update_window.lift();return
        d,f=dialog(self.root,'Update MDM',650);d.geometry('650x560');self.update_window=d
        label(f,'App and download tools update separately.',11,MUTED).pack(fill='x',pady=(0,14))
        app=tk.Frame(f,bg=CARD,padx=16,pady=14,highlightthickness=1,highlightbackground=BORDER);app.pack(fill='x',pady=(0,12))
        label(app,'App update',15).pack(fill='x')
        label(app,'Windows '+__version__+'  ·  Your GitHub releases',10,MUTED).pack(fill='x',pady=5)
        label(app,updater.get_repository() or 'Add your GitHub owner/repository in App update.',10,MUTED,wraplength=550).pack(fill='x')
        app_button=button(app,'Open app update',self.app_updates);app_button.pack(anchor='w',pady=(9,0))
        tools=tk.Frame(f,bg=CARD,padx=16,pady=14,highlightthickness=1,highlightbackground=BORDER);tools.pack(fill='both',expand=True)
        label(tools,'Download tools',15).pack(fill='x')
        versions=label(tools,'Reading installed versions…',10,MUTED,justify='left',wraplength=550);versions.pack(fill='x',pady=7)
        label(tools,'yt-dlp, EJS, Deno, FFmpeg / ffprobe and Google Drive support.',10,MUTED,wraplength=550).pack(fill='x')
        state=label(tools,'',10,MINT,wraplength=550,justify='left');state.pack(fill='x',pady=8)
        bar=ttk.Progressbar(tools,maximum=1);bar.pack(fill='x')
        def got_versions(data):
            if d.winfo_exists():
                lines=['yt-dlp '+data.get('yt-dlp','?')+'  ·  EJS '+data.get('yt-dlp-ejs','?')+'  ·  Drive '+data.get('gdown','?'),
                       data.get('Deno','?')+'  ·  '+data.get('FFmpeg','?')]
                versions.config(text='\n'.join(lines))
        def load_versions():self.call({'action':'tools_versions'},got_versions,lambda e:None)
        def start():
            update_button.config(state='disabled');state.config(text='Starting tool update…',fg=MINT)
            def failed(e):
                if d.winfo_exists():update_button.config(state='normal');state.config(text=e[:400],fg=ERROR)
            self.call({'action':'tools_update'},lambda _:None,failed)
        update_button=button(tools,'Check & update tools',start,True);update_button.pack(anchor='w',pady=(10,0))
        was_busy={'value':False}
        def poll():
            if not d.winfo_exists():return
            def got(data):
                if not d.winfo_exists():return
                busy=data['busy'];update_button.config(state='disabled' if busy else 'normal');app_button.config(state='disabled' if busy else 'normal')
                state.config(text=(data.get('error') or data.get('message') or 'Updates use official sources. Downloads resume after switching tools.')[:450],fg=ERROR if data.get('error') else MINT)
                bar['value']=data.get('progress',0)
                if was_busy['value'] and not busy:load_versions()
                was_busy['value']=busy;d.after(1200,poll)
            def failed(e):
                if d.winfo_exists():state.config(text=e[:300],fg=ERROR);d.after(2000,poll)
            self.call({'action':'tools_status'},got,failed)
        load_versions();poll()

    def app_updates(self):
        from . import updater
        d,f=dialog(self.root,'Check for updates');d.geometry('590x380')
        label(f,'Trusted public GitHub repository: owner/repository',10,MUTED).pack(fill='x');repo=entry(f,updater.get_repository());repo.pack(fill='x',ipady=8,pady=10)
        label(f,'A newer Windows release will download and install when you check. Downloads pause, then MDM restarts.',11,MUTED,wraplength=530,justify='left').pack(fill='x',pady=10)
        status=label(f,'',10,MINT,wraplength=530);status.pack(fill='x',pady=12);bar=ttk.Progressbar(f,maximum=1);bar.pack(fill='x')
        def begin():
            self.updating=True;start.config(state='disabled');repo.config(state='disabled');d.protocol('WM_DELETE_WINDOW',lambda:None)
            def progress(text,value):self.events.put((lambda pair:(status.config(text=pair[0]),bar.configure(value=pair[1])),(text,value)))
            def done(result):
                self.updating=False
                if result.get('installer'):
                    subprocess.Popen([result['installer'],'/UPDATE'],close_fds=True);self.root.destroy()
                else:status.config(text='You already have the latest Windows version.');reset()
            def reset():
                self.updating=False;start.config(state='normal');repo.config(state='normal');d.protocol('WM_DELETE_WINDOW',d.destroy)
            def fail(e):status.config(text=e[:350]);reset()
            value=repo.get();self.work(lambda:updater.check_and_download(value,progress),done,fail)
        start=button(f,'Check & install update',begin,True);start.pack(fill='x',pady=16)

def run(updated=False):
    from .common import init_state
    from .platform_support import filelocks
    init_state()
    with open(STATE/'gui.lock','a+') as lock:
        try:filelocks.flock(lock,filelocks.LOCK_EX|filelocks.LOCK_NB)
        except BlockingIOError:return 0
        root=tk.Tk();Window(root,updated);root.mainloop();return 0
