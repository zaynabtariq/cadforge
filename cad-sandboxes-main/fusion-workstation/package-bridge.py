#!/usr/bin/env python3
"""Package the included add-in source for installation on your own workstation."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
source = root / 'bridge-package'
destination = root / 'bridge-package.zip'
with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.manifest'):
            archive.write(path, path.relative_to(source))
print('Created bridge-package.zip from the included source.')
