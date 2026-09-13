import pytest
from cadforge.providers import wandb_client, typesafe_client, IntegrationUnavailable
from cadforge.telemetry import enable_weave
from cadforge.planner import parse_request

def test_missing_integrations_fail_explicitly(monkeypatch):
    monkeypatch.delenv('WANDB_API_KEY',raising=False)
    monkeypatch.delenv('CADFORGE_WEAVE_PROJECT',raising=False)
    with pytest.raises(IntegrationUnavailable): wandb_client()
    with pytest.raises(IntegrationUnavailable,match='different product'): typesafe_client()
    assert not enable_weave()['enabled']

def test_natural_language_units_and_unknown():
    spec=parse_request('Create bracket width 4 cm, wall=2 mm')
    assert spec.parameters == {'width':40,'wall':2}
    with pytest.raises(ValueError): parse_request('Create a turbine')
    with pytest.raises(ValueError): parse_request('Create an enclosure and bracket')
