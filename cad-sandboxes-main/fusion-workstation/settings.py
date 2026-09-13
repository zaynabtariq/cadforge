"""Deployment configuration supplied by the operator, never committed state."""
import json
import os
from pathlib import Path
import re


def deployment():
    path = Path(os.environ.get('FUSION_DEPLOYMENT_CONFIG') or Path(__file__).with_name('deployment.json')).expanduser()
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError):
        raise RuntimeError('Copy deployment.example.json to deployment.json and configure your AWS network first.') from None
    for field, pattern in [('vpc_id', r'vpc-[0-9a-f]{8,17}'), ('subnet_id', r'subnet-[0-9a-f]{8,17}')]:
        if not re.fullmatch(pattern, config.get(field, '')):
            raise RuntimeError(f'Configure {field} in deployment.json before provisioning.')
    if not config.get('region') or not config.get('name'):
        raise RuntimeError('Configure region and name in deployment.json before provisioning.')
    return config
