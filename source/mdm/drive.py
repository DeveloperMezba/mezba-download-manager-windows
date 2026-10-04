"""Public Drive single-file adapter. Runs as a supervised child process."""
import inspect
import json
from pathlib import Path
import sys
import time
import gdown

url, folder, filename, speed, retries = sys.argv[1:]
output = str(Path(folder)) + '/' if filename == 'Google-Drive-file' else str(Path(folder) / filename)
last_time, last_bytes = time.monotonic(), 0

def progress(done, total):
    global last_time, last_bytes
    now = time.monotonic()
    if now - last_time < .5 and done != total:
        return
    rate = max(0, done - last_bytes) / max(.001, now - last_time)
    print('MDM_PROGRESS ' + json.dumps({'downloaded_bytes': done, 'total_bytes': total, 'speed': rate}), flush=True)
    last_time, last_bytes = now, done

parameters = inspect.signature(gdown.download).parameters
options = {'url': url, 'output': output, 'quiet': True, 'resume': True, 'use_cookies': False}
if 'fuzzy' in parameters:
    options['fuzzy'] = True
if 'speed' in parameters and int(speed):
    options['speed'] = int(speed) * 1024
if 'progress' in parameters:
    options['progress'] = progress
if 'retries' in parameters:
    options['retries'] = int(retries)
if 'timeout' in parameters:
    options['timeout'] = (20, 30)
result = gdown.download(**options)
if not result or not Path(result).is_file():
    raise SystemExit('Drive did not produce a file. Check that it is a public single-file link and is not quota blocked.')
print('MDM_FILE ' + json.dumps(str(result)), flush=True)
