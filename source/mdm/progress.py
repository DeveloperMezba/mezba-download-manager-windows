import re
import tkinter as tk
from .gui import UI,ProgressWindow

def run(task_id):
    if not re.fullmatch('[0-9a-f]{12}',task_id):raise ValueError('Invalid download ID')
    root=tk.Tk();ui=UI(root);ProgressWindow(ui,task_id,True);root.mainloop();return 0
