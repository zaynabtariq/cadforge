#!/usr/bin/env python3
"""Get a single-part JLC3DP estimate using only the browse CLI and rendered DOM."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
URL = 'https://jlc3dp.com/3d-printing-quote'
TECHNOLOGIES = {'SLA': 'SLA(Resin)', 'FDM': 'FDM(Plastic)', 'MJF': 'MJF(Nylon)',
                'SLS': 'SLS(Nylon)', 'SLM': 'SLM(Metal)', 'WJP': 'WJP(Resin)', 'BJ': 'BJ(Metal)'}
CATEGORIES = {
    'blocks': 'Enclosure、Block、Plate、Cylinder、Category',
    'connectors': 'Connectors、Brackets、fasteners Category',
    'irregular': 'Irregular shape Category',
    'office': 'Office Appliance and Accessories',
    'toys': 'Toy and Entertainment',
}
INVALID = re.compile(r'unavailable|please deselect|cannot be printed|not supported|too small|too large|exceeds|failed|invalid file', re.I)
MONEY = r'\$([\d,]+\.\d{2})'


class Browser:
    def __init__(self, session):
        self.session = session

    def call(self, *args):
        # Argument arrays preserve filenames and JS literally; no shell interpolation.
        p = subprocess.run(['browse', *args, '--session', self.session],
                           capture_output=True, text=True, timeout=65)
        if p.returncode:
            raise RuntimeError(f'browse {args[0]} failed: {p.stderr.strip()} {p.stdout.strip()}')
        value = json.loads(p.stdout)
        if value.get('error'):
            raise RuntimeError(str(value['error']))
        return value

    def state(self):
        return self.call('eval', (ROOT / 'page-state.js').read_text())['result']

    def snapshot(self):
        return self.call('snapshot')['tree']

    def ref(self, role, name):
        deadline = time.monotonic() + 20
        while True:
            tree = self.snapshot()
            matches = re.findall(r'^\s*\[([^]]+)\] ' + re.escape(role) + ': ' +
                                 re.escape(name) + r'\s*$', tree, re.M)
            if matches or time.monotonic() >= deadline:
                break
            time.sleep(1)
        if len(matches) != 1:
            raise RuntimeError(f'Expected one {role} named {name!r}, found {len(matches)}')
        return '@' + matches[0]

    def click(self, role, name):
        for attempt in range(3):
            ref = self.ref(role, name)
            try:
                return self.call('click', ref)
            except RuntimeError as exc:
                # browse can invalidate refs while the page hydrates. Unknown-ref
                # failures happen before interaction, so resolving again is safe.
                if 'Unknown ref' not in str(exc) or attempt == 2:
                    raise
                time.sleep(1)

    def wait(self, predicate, label, timeout=90, stable=0):
        deadline = time.monotonic() + timeout
        since = None
        last = None
        while time.monotonic() < deadline:
            state = self.state()
            value = predicate(state)
            if value:
                if value != last:
                    since = time.monotonic()
                if time.monotonic() - since >= stable:
                    return state
            else:
                since = None
            last = value
            time.sleep(1)
        raise RuntimeError(f'Timed out waiting for {label}')


def amount(text, pattern):
    match = re.search(pattern, text)
    return Decimal(match.group(1).replace(',', '')) if match else None


def prices(state):
    text = state['text']
    row = amount(text, r'Edit Specifications\s*' + MONEY)
    total = amount(text, r'Charge Details\s*Total Price\s*' + MONEY)
    shipping = amount(text, r'Shipping Estimate\s*' + MONEY)
    return row, total, shipping


def stable_quote(state, filename, quantity, require_shipping=False):
    row, total, shipping = prices(state)
    if (state['loading'] or state['dialog'] or filename not in state['text'] or
            'Select All (1)' not in state['text'] or
            state['quantities'] != [str(quantity)] or total is None or total <= 0 or row != total or
            (require_shipping and shipping is None)):
        return False
    return (str(total), str(shipping), state['text'])


def configure(browser, args):
    browser.click('button', 'Edit Specifications')
    browser.wait(lambda s: bool(s['dialog']), 'specification dialog')
    browser.click('button', TECHNOLOGIES[args.technology])
    browser.wait(lambda s: s['dialog'] and TECHNOLOGIES[args.technology] in s['dialog']['selected'],
                 'technology selection')
    browser.click('button', args.material)
    browser.wait(lambda s: s['dialog'] and args.material in s['dialog']['selected'], 'material selection')
    if args.color:
        browser.click('button', args.color)
    # Quantity is edited in the dialog; the product description enables Save.
    browser.snapshot()
    browser.call('fill', '[role=dialog] input[role=spinbutton]', str(args.quantity))
    browser.call('press', 'Tab')
    # The last Select field in this dialog is the observed Product Desc cascader.
    browser.call('click', '(//*[@role="dialog"]//input[@placeholder="Select"])[last()]')
    browser.click('menuitem', CATEGORIES[args.category])
    browser.click('menuitem', 'others')
    browser.call('fill', browser.ref('textbox', 'Enter a clear description'), args.description)
    state = browser.wait(
        lambda s: s['dialog'] and not s['loading'] and
        amount(s['dialog']['text'], r'\nPrice\s*' + MONEY) is not None and
        (s['dialog']['text'], json.dumps(s['dialog']['inputs'], sort_keys=True)),
        'configured price', stable=4)
    warning_lines = [line.strip() for line in state['dialog']['text'].splitlines() if INVALID.search(line)]
    if warning_lines:
        raise RuntimeError('Manufacturing configuration rejected: ' + ' | '.join(warning_lines))
    selection = state['dialog']
    if not any(i['value'] == args.description for i in selection['inputs']):
        raise RuntimeError('Product description was altered or truncated by the form')
    if args.color and args.color not in selection['selected']:
        raise RuntimeError('Requested color was not selected')
    browser.click('button', 'Save')
    browser.wait(lambda s: s['dialog'] is None, 'saved specifications', timeout=20)
    state = browser.wait(lambda s: stable_quote(s, args.file.name, args.quantity),
                         'matching part and total prices', stable=4)
    if args.material not in state['text']:
        raise RuntimeError('Saved part does not show the requested material')
    # Reopen after saving to verify persistence, not just a changed dialog preview.
    browser.click('button', 'Edit Specifications')
    saved = browser.wait(lambda s: s['dialog'] and args.material in s['dialog']['selected'],
                         'persisted configuration')['dialog']
    if (TECHNOLOGIES[args.technology] not in saved['selected'] or
            not any(i['role'] == 'spinbutton' and i['value'] == str(args.quantity) for i in saved['inputs']) or
            not any(i['value'] == args.description for i in saved['inputs']) or
            (args.color and args.color not in saved['selected'])):
        raise RuntimeError('Saved configuration does not match the request')
    browser.click('button', 'Close')
    return saved


def run(args, browser, artifact_dir):
    print('Opening a fresh JLC3DP browser session…', file=sys.stderr)
    browser.call('open', URL, '--local')
    browser.wait(lambda s: 'Online 3D Printing Quote' in s['text'] and 'Explore the Demo' in s['text'],
                 'empty quote page')
    # Explicitly inspect the region instead of treating an IP-derived shipping quote as universal.
    browser.click('StaticText', 'USD')
    tree = browser.snapshot()
    if 'button: United States Of America' not in tree or 'button: USD $' not in tree:
        raise RuntimeError('This prototype expects the United States / USD site region')
    browser.click('button', 'Save')
    browser.snapshot()
    print(f'Uploading {args.file.name}…', file=sys.stderr)
    browser.call('upload', 'input[type=file]', str(args.file))
    browser.wait(lambda s: stable_quote(s, args.file.name, 1), 'uploaded model quote', stable=3)
    print(f'Configuring {args.quantity} × {args.material}…', file=sys.stderr)
    config = configure(browser, args)
    # Shipping is optional; a missing estimate must never become a zero-dollar charge.
    try:
        state = browser.wait(lambda s: stable_quote(s, args.file.name, args.quantity, True),
                             'regional shipping estimate', timeout=35, stable=5)
    except RuntimeError as exc:
        if not str(exc).startswith('Timed out'):
            raise
        state = browser.wait(lambda s: stable_quote(s, args.file.name, args.quantity),
                             'manufacturing quote', stable=3)
    text = state['text']
    _, total, shipping = prices(state)
    dimensions = re.search(r'([\d.]+)×([\d.]+)×([\d.]+) cm', text)
    build = re.search(r'Build Time\s*(.*?)\n\s*\*', text, re.S)
    shipping_block = text.split('Shipping Estimate', 1)[-1].split('Coupons', 1)[0].strip()
    selected_build = browser.call('eval',
        'Array.from(document.querySelectorAll("main input[type=radio]:checked"))'
        '.map(e=>e.closest("label")?.innerText.trim())')['result']
    result = {
        'status': 'estimated', 'provider': 'JLC3DP', 'source_url': URL,
        'quoted_at': datetime.now(timezone.utc).isoformat(),
        'file': args.file.name, 'file_sha256': hashlib.sha256(args.file.read_bytes()).hexdigest(),
        'quantity': args.quantity, 'technology': args.technology, 'material': args.material,
        'requested_color': args.color, 'description': args.description, 'category': args.category,
        'configuration': config, 'currency': 'USD',
        'dimensions_mm': [float(x) * 10 for x in dimensions.groups()] if dimensions else None,
        'manufacturing_subtotal': str(total),
        'average_unit_price': str((total / args.quantity).quantize(Decimal('0.0001'))),
        'build_time': selected_build or ([build.group(1).strip()] if build else []),
        'shipping': {
            'status': 'regional_estimate' if shipping is not None else 'unavailable',
            'country': 'United States Of America', 'address_verified': False,
            'amount': str(shipping) if shipping is not None else None,
            'details': shipping_block,
        },
        'estimated_manufacturing_plus_shipping': str(total + shipping) if shipping is not None else None,
        'checkout_total': None,
        'warnings': [
            'Online estimate; final manufacturing price is subject to provider review.',
            'Shipping is a country-level estimate; no delivery address has been entered.',
            'Taxes, duties, and other checkout adjustments have not been verified.',
        ],
        'browser_session': browser.session if args.keep_browser else None,
        'artifacts': str(artifact_dir),
    }
    (artifact_dir / 'quote.json').write_text(json.dumps(result, indent=2) + '\n')
    (artifact_dir / 'error.json').unlink(missing_ok=True)
    (artifact_dir / 'page-state.json').write_text(json.dumps(state, indent=2) + '\n')
    (artifact_dir / 'snapshot.txt').write_text(browser.snapshot() + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--technology', choices=TECHNOLOGIES, default='SLA')
    parser.add_argument('--material', default='9600 Resin', help='Exact visible JLC3DP material name')
    parser.add_argument('--color', help='Exact visible color name; otherwise retain provider default')
    parser.add_argument('--quantity', type=int, default=1)
    parser.add_argument('--category', choices=CATEGORIES, required=True)
    parser.add_argument('--description', required=True, help='Accurate plain-language part description')
    parser.add_argument('--artifact-dir', type=Path)
    parser.add_argument('--keep-browser', action='store_true')
    args = parser.parse_args()
    args.file = args.file.expanduser().resolve()
    if not args.file.is_file() or args.file.suffix.lower() not in {'.stl', '.stp', '.step', '.obj', '.3mf'}:
        parser.error('Provide an existing STL, STEP/STP, OBJ, or 3MF file')
    if not 1 <= args.quantity <= 100000 or not args.description.strip():
        parser.error('Quantity must be 1–100000 and description must be nonempty')
    if len(args.description.encode('utf-16-le')) // 2 > 30:
        parser.error('JLC3DP limits custom descriptions to 30 characters')
    if not shutil.which('browse'):
        parser.error('Install the browse CLI before running this adapter')
    session = 'jlc-' + uuid.uuid4().hex[:10]
    artifact_dir = (args.artifact_dir or ROOT / 'artifacts' / session).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    browser = Browser(session)
    try:
        result = run(args, browser, artifact_dir)
        print(json.dumps(result, indent=2))
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError) as exc:
        result = {'status': 'error', 'error': str(exc), 'artifacts': str(artifact_dir)}
        (artifact_dir / 'quote.json').unlink(missing_ok=True)
        (artifact_dir / 'error.json').write_text(json.dumps(result, indent=2) + '\n')
        try:
            (artifact_dir / 'snapshot.txt').write_text(browser.snapshot() + '\n')
            (artifact_dir / 'page-state.json').write_text(json.dumps(browser.state(), indent=2) + '\n')
        except Exception:
            pass
        print(json.dumps(result, indent=2))
        return 1
    finally:
        if not args.keep_browser:
            try:
                browser.call('stop')
            except Exception as exc:
                print(f'Browser cleanup: {exc}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
