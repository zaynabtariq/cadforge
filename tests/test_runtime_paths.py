from pathlib import Path
import pytest
from cadforge import runtime_paths


def test_installed_package_uses_user_data_not_install_parent(tmp_path,monkeypatch):
    monkeypatch.delenv('CADFORGE_ARTIFACTS_DIR',raising=False)
    monkeypatch.setattr(runtime_paths,'__file__',str(tmp_path/'lib/python3.11/site-packages/cadforge/runtime_paths.py'))
    assert runtime_paths.artifact_directory()==Path.home()/'.local/share/cadforge/artifacts'


def test_checkout_preserves_existing_artifact_location(tmp_path,monkeypatch):
    monkeypatch.delenv('CADFORGE_ARTIFACTS_DIR',raising=False)
    (tmp_path/'pyproject.toml').write_text('[project]')
    monkeypatch.setattr(runtime_paths,'__file__',str(tmp_path/'src/cadforge/runtime_paths.py'))
    assert runtime_paths.artifact_directory()==tmp_path/'artifacts'


def test_explicit_destination_wins(tmp_path,monkeypatch):
    monkeypatch.setenv('CADFORGE_ARTIFACTS_DIR',str(tmp_path/'data'))
    assert runtime_paths.artifact_directory()==tmp_path/'data'

@pytest.mark.parametrize('path',['',' ','relative/path'])
def test_ambiguous_override_rejects(monkeypatch,path):
    monkeypatch.setenv('CADFORGE_ARTIFACTS_DIR',path)
    with pytest.raises(ValueError):runtime_paths.artifact_directory()
