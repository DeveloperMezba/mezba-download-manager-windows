#!/usr/bin/env python3
import argparse
import importlib.util
import json
import shutil
import sys

def main():
    import os
    from pathlib import Path
    root=Path(__file__).resolve().parent.parent
    os.environ['PATH']=str(root/'runtime')+os.pathsep+str(root/'tools')+os.pathsep+os.environ.get('PATH','')
    from mdm_components import activate
    activate()
    if (root/'runtime/tcl/tcl8.6').is_dir():os.environ['TCL_LIBRARY']=str(root/'runtime/tcl/tcl8.6')
    if (root/'runtime/tcl/tk8.6').is_dir():os.environ['TK_LIBRARY']=str(root/'runtime/tcl/tk8.6')

    parser = argparse.ArgumentParser(description='Mezba Download Manager')
    parser.add_argument('--daemon', action='store_true')
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--doctor', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--add', metavar='URL')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--progress', metavar='TASK_ID')
    parser.add_argument('--updated', action='store_true')
    args = parser.parse_args()
    if args.native:
        from mdm.native import run
        run()
    elif args.progress:
        from mdm.progress import run
        return run(args.progress)
    elif args.daemon:
        from mdm.service import serve
        serve()
    elif args.doctor:
        from mdm import __version__
        print('MDM', __version__, '\nPython:', sys.version.split()[0])
        for module in ('tkinter', 'yt_dlp', 'gdown'):
            print(module + ':', 'available' if importlib.util.find_spec(module) else 'MISSING')
        for tool in ('ffmpeg', 'deno', 'node', 'qjs', 'xdg-open'):
            print(tool + ':', shutil.which(tool) or 'not installed')
        print('YouTube needs Deno >=2.3, Node >=22, or a supported QuickJS. Check its --version.')
    elif args.stop or args.list or args.add:
        from mdm.service import request
        message = {'action': 'shutdown' if args.stop else 'list'}
        if args.add:
            message = {'action': 'add', 'url': args.add, 'kind': 'media' if args.video else 'file'}
        try:
            print(json.dumps(request(message, autostart=not args.stop), indent=2))
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1
    else:
        try:
            from mdm.gui import run
        except ImportError:
            print('The MDM runtime is incomplete. Run the Windows installer again.', file=sys.stderr)
            return 1
        return run(updated=args.updated)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
