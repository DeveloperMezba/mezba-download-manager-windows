"""Persistent native messaging host; browser actions are explicitly allowlisted."""
import json
import re
import struct
import subprocess
import sys
from .common import BASE
from .platform_support import open_folder, gui_python, hidden_process, spawn_background
from .service import request

PUBLIC_FIELDS = ('id','title','status','done','total','speed','error','quality',
                 'playlist_index','playlist_count','item_title','start_at')

def dispatch(message):
    if not isinstance(message, dict):
        raise ValueError('Expected an object')
    action = message.get('action')
    if action not in ('ping','analyze','add','open','status','pause','resume','folder'):
        raise ValueError('Action is not allowed from the browser.')
    if action == 'open':
        spawn_background([gui_python(),'-X','utf8',str(BASE/'mdm.py')],stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return True
    if action in ('status','pause','resume','folder'):
        task_id = message.get('id','')
        if not isinstance(task_id,str) or not re.fullmatch('[0-9a-f]{12}',task_id):
            raise ValueError('Invalid download ID')
        task = request({'action':'get' if action in ('status','folder') else action,'id':task_id})
        if action == 'folder':
            from pathlib import Path
            folder=Path(task['folder']);folder.mkdir(parents=True,exist_ok=True)
            open_folder(folder)
            return True
        return {key:task.get(key) for key in PUBLIC_FIELDS}
    clean={k:v for k,v in message.items() if k in ('action','url','kind','quality','title','filename')}
    result=request(clean)
    return {'id':result['id'],'title':result['title']} if action=='add' else result

def run():
    if sys.platform == 'win32':
        import msvcrt, os
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    while True:
        header=sys.stdin.buffer.read(4)
        if not header:return
        if len(header)!=4:return
        length=struct.unpack('=I',header)[0]
        if length>65536:return
        data=sys.stdin.buffer.read(length)
        if len(data)!=length:return
        request_id=None
        try:
            message=json.loads(data)
            request_id=message.get('request_id') if isinstance(message,dict) else None
            if request_id is not None and (not isinstance(request_id,(int,str)) or len(str(request_id))>40):
                raise ValueError('Invalid request ID')
            response={'ok':True,'result':dispatch(message)}
        except Exception as e:
            response={'ok':False,'error':str(e)[:3000]}
        if request_id is not None:response['request_id']=request_id
        encoded=json.dumps(response).encode()
        sys.stdout.buffer.write(struct.pack('=I',len(encoded))+encoded)
        sys.stdout.buffer.flush()
