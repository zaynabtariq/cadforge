import json
from cadforge.development_status import development_status


def test_incomplete_latest_comparison_is_visible(tmp_path):
    folder=tmp_path/'artifacts/access-retrieval-comparison/new';folder.mkdir(parents=True)
    (folder/'contract.json').write_text('{}')
    result=development_status(tmp_path)
    assert 'error' in result['comparison']
    assert 'FileNotFoundError' in result['comparison']['error']


def test_legacy_costs_are_recovered_from_retained_trials(tmp_path):
    folder=tmp_path/'artifacts/tool-access-learning/legacy';folder.mkdir(parents=True)
    (folder/'summary.json').write_text('{"discovery_trials":2}')
    (folder/'discovery').mkdir();(folder/'verify').mkdir();(folder/'comparison').mkdir()
    (folder/'discovery/a.json').write_text(json.dumps({'trials':[{},{}]}))
    (folder/'verify/b.json').write_text(json.dumps({'trials':[{}]}))
    result=development_status(tmp_path)
    assert result['tool_access_runs'][0]=={'run':'legacy','discovery_trials':2,'verification_trials':1,'comparison_trials':0}
    (folder/'summary.json').write_text('{"discovery_trials":1}')
    assert 'error' in development_status(tmp_path)['tool_access_runs'][0]
