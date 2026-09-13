#!/usr/bin/env python3
"""Run an existing Fusion CLI against the SSH-forwarded bridge, without editing it."""
import ast,os,re,sys
from pathlib import Path
from urllib.parse import urlsplit

if len(sys.argv)<2:
    raise SystemExit('Usage: python3 fusion-cli.py fusion-nav state --sparse')
name=sys.argv[1]
modeling_root=os.environ.get('FUSION_MODELING_ROOT')
if not modeling_root:raise SystemExit('Set FUSION_MODELING_ROOT to your external modeling CLI installation.')
source_root=Path(modeling_root).expanduser()/'tools'
if not re.fullmatch(r'fusion-[a-z0-9-]+', name):
    raise SystemExit('Expected an existing fusion-* tool name')
path=source_root/name
if not path.is_file():raise SystemExit(f'Fusion tool not found: {name}. Check FUSION_MODELING_ROOT.')
source=path.read_text()
endpoint=os.environ.get('FUSION_BRIDGE_URL','').rstrip('/')
if not endpoint:raise SystemExit('Select a workstation with workstation.py run, or set FUSION_BRIDGE_URL explicitly.')
parsed=urlsplit(endpoint)
if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit('FUSION_BRIDGE_URL must be an HTTP(S) URL')
tree=ast.parse(source,filename=str(path));changed=False
for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BRIDGE' for t in node.targets):
        node.value=ast.Constant(endpoint);changed=True
if not changed:raise SystemExit(f'{name} does not expose a BRIDGE setting; invoke its own remote configuration instead')
ast.fix_missing_locations(tree)
sys.argv=[str(path),*sys.argv[2:]]
sys.path.insert(0,str(source_root))
exec(compile(tree,str(path),'exec'),{'__name__':'__main__','__file__':str(path)})
