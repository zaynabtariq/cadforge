#!/usr/bin/env python3
"""Use the normal AWS credential chain, with an optional operator-owned env file."""
import os, shlex, subprocess, sys
from pathlib import Path

def aws_env():
    env = dict(os.environ)
    if env.get('FUSION_USE_INSTANCE_ROLE') == '1':
        for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE'):
            env.pop(key, None)
        env['AWS_PAGER'] = ''
        return env
    config = env.get('FUSION_AWS_ENV_FILE')
    lines = Path(config).expanduser().read_text().splitlines() if config else []
    for line in lines:
        key, sep, value = line.partition('=')
        key = key.strip().removeprefix('export ')
        if sep and key.startswith('AWS_'):
            parts = shlex.split(value, comments=True)
            if parts: env.setdefault(key, parts[0])
    env['AWS_PAGER'] = ''
    return env

if __name__ == '__main__':
    raise SystemExit(subprocess.call(['aws', *sys.argv[1:]], env=aws_env()))
