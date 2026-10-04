"""Select a verified, versioned tool bundle without replacing loaded packages."""
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
DIRECTORY = ROOT / 'components'
_paths = []
_tool_path = None


def selected():
    try:
        data = json.loads((DIRECTORY / 'current.json').read_text(encoding='utf-8'))
        name = data['bundle']
        if not isinstance(name, str) or not re.fullmatch(r'bundle-[0-9a-f]{32}', name):
            return None
        path = DIRECTORY / name
        if (path / 'packages').is_dir() and (path / 'tools').is_dir():
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def activate():
    global _paths, _tool_path
    for path in _paths:
        while path in sys.path:
            sys.path.remove(path)
    _paths = []
    paths = os.environ.get('PATH', '').split(os.pathsep)
    if _tool_path:
        paths = [p for p in paths if p != _tool_path]
    bundle = selected()
    _tool_path = None
    if bundle:
        _paths = [str(bundle / 'packages')]
        sys.path[:0] = _paths
        _tool_path = str(bundle / 'tools')
        paths = [p for p in paths if p != _tool_path]
        paths.insert(0, _tool_path)
    os.environ['PATH'] = os.pathsep.join(paths)
    return bundle
