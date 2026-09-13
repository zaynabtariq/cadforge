"""Writable runtime data never derives from an installed library directory."""
import os
from pathlib import Path


def artifact_directory():
    override=os.getenv('CADFORGE_ARTIFACTS_DIR')
    if override is not None:
        path=Path(override).expanduser()
        if not override.strip() or not path.is_absolute():
            raise ValueError('CADFORGE_ARTIFACTS_DIR must be a nonempty absolute path')
        return path.resolve()
    module=Path(__file__).resolve()
    checkout=module.parents[2]
    if module.parent.parent.name=='src' and (checkout/'pyproject.toml').is_file():
        return checkout/'artifacts'
    return Path.home()/'.local/share/cadforge/artifacts'
