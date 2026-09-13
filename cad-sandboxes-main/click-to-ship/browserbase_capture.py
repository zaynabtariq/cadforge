"""Browserbase recording downloads. Credentials stay in the server process."""
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def load_credentials(path):
    for line in Path(path).expanduser().read_text().splitlines():
        key, sep, value = line.strip().removeprefix('export ').partition('=')
        if sep and key.strip() in ('BROWSERBASE_API_KEY', 'BROWSERBASE_PROJECT_ID'):
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))
    if not os.environ.get('BROWSERBASE_API_KEY'):
        raise RuntimeError('BROWSERBASE_API_KEY is required for recorded sessions')


def request(path, method='GET'):
    req = Request('https://api.browserbase.com/v1/' + path, method=method,
                  headers={'X-BB-API-Key': os.environ['BROWSERBASE_API_KEY']})
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not include signed URLs or API response bodies in UI errors.
        raise RuntimeError(f'Browserbase recording API returned HTTP {exc.code}') from None


def capture(session_id, directory, update):
    """Called after the worker disconnects; archive every recorded tab locally."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    update(status='processing', message='Browserbase is preparing the recording')
    try:
        endpoint = f'sessions/{session_id}/recording/downloads'
        deadline = time.monotonic() + 240
        while True:
            try:
                request(endpoint, 'POST')
                break
            except RuntimeError as exc:
                if 'HTTP 409' not in str(exc) or time.monotonic() >= deadline:
                    raise
                time.sleep(3)
        while time.monotonic() < deadline:
            pages = request(endpoint).get('downloads', [])
            if any(p['status'] == 'FAILED' for p in pages):
                raise RuntimeError('Browserbase could not assemble this recording')
            if pages and all(p['status'] == 'COMPLETED' for p in pages):
                break
            time.sleep(3)
        else:
            raise RuntimeError('Recording is still processing; view it in Browserbase')
        saved = []
        for page in pages:
            page_id = str(page['pageId'])
            if not re.fullmatch(r'[A-Za-z0-9_-]+', page_id):
                raise RuntimeError('Unexpected recording page identifier')
            if not page.get('downloadUrl', '').startswith('https://'):
                raise RuntimeError('No recording download URL is available')
            target = directory / f'{page_id}.mp4'
            temporary = target.with_suffix('.partial')
            with urlopen(page['downloadUrl'], timeout=90) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            temporary.replace(target)
            saved.append({'page_id': page_id, 'bytes': target.stat().st_size})
        metadata = {'session_id': session_id, 'pages': saved}
        (directory / 'recording.json').write_text(json.dumps(metadata, indent=2) + '\n')
        update(status='ready', message='Recording saved · replay the quote flow', pages=saved)
    except Exception as exc:
        # Network exceptions may contain signed download URLs.
        message = str(exc) if isinstance(exc, RuntimeError) else 'Recording download failed; view it in Browserbase'
        update(status='error', message=message)
