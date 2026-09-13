"""One persistent JLC3DP browser, owned exclusively by a session's worker."""
import re
import os
import threading

from browserbase_capture import capture

from quote import Browser, URL, TECHNOLOGIES, CATEGORIES, INVALID, prices, stable_quote


class SessionBrowser(Browser):
    checkpoint = None

    def call(self, *args):
        # Finish an in-flight CLI action, then yield before the next action or poll.
        if self.checkpoint and args[0] != 'stop':
            self.checkpoint()
        try:
            return super().call(*args)
        except RuntimeError as exc:
            message = str(exc)
            key = os.environ.get('BROWSERBASE_API_KEY')
            if key:
                message = message.replace(key, '[redacted]')
            message = re.sub(r'wss?://[^\s"\']+', '[browser connection]', message)
            raise RuntimeError(message) from None


class JLCAdapter:
    def __init__(self, session_id, file):
        self.browser = SessionBrowser('web-' + session_id)
        self.file = file
        self.saved_category = None
        self.remote = os.environ.get('QUOTE_BROWSER') == 'browserbase'
        self.browser_info = {'status': 'starting' if self.remote else 'local',
                             'message': 'Connecting to Browserbase' if self.remote else 'Recording requires Browserbase mode'}
        self.info_lock = threading.Lock()

    def update_browser(self, **patch):
        with self.info_lock:
            self.browser_info = {**self.browser_info, **patch}

    def browser_snapshot(self):
        with self.info_lock:
            return dict(self.browser_info)

    def close(self):
        try:
            self.browser.call('stop')
        finally:
            if self.browser_info.get('session_id'):
                capture(self.browser_info['session_id'], self.file.parent.parent / 'recording', self.update_browser)

    def bootstrap(self, progress, checkpoint):
        b = self.browser
        b.checkpoint = checkpoint
        progress('starting', 'Connecting to JLC3DP')
        opened = b.call('open', URL, '--remote' if self.remote else '--local')
        if self.remote:
            session_id = opened.get('browserbaseSessionId') or b.call('status').get('browserbaseSessionId')
            if not session_id:
                raise RuntimeError('Browserbase did not return a session identifier')
            self.update_browser(session_id=session_id,
                                dashboard_url=f'https://www.browserbase.com/sessions/{session_id}')
            self.update_browser(status='live', message='Recording the JLC3DP quote flow')
            progress('starting', 'Browserbase connected · recording the quote flow')
            b.call('cursor')
        b.wait(lambda s: 'Explore the Demo' in s['text'], 'empty upload page')
        checkpoint()
        b.click('StaticText', 'USD')
        if 'button: United States Of America' not in b.snapshot():
            raise RuntimeError('This prototype currently requires the US / USD site region')
        b.click('button', 'Save')
        progress('uploading', 'Uploading and analyzing your model')
        b.snapshot()
        b.call('upload', 'input[type=file]', str(self.file))
        state = b.wait(lambda s: stable_quote(s, self.file.name, 1), 'model analysis', stable=2)
        checkpoint()
        fields = self.dialog()['fields']
        self.initial_options = fields
        default_config = {
            'technology': fields['3D Technology']['selected'][0].split('(')[0],
            'material': fields['Material']['selected'][0],
            'color': (fields.get('Color', {}).get('selected') or [None])[0], 'quantity': 1,
        }
        return self.quote_data(state, default_config, baseline=True)

    def dialog(self):
        b = self.browser
        if not b.state()['dialog']:
            b.click('button', 'Edit Specifications')
        return b.wait(lambda s: s['dialog'] and s['dialog']['fields'].get('Material'),
                      'material options')['dialog']

    def inspect(self, config, progress, checkpoint):
        b = self.browser
        b.checkpoint = checkpoint
        progress('configuring', 'Checking available materials and settings')
        d = self.dialog()
        checkpoint()
        technology = TECHNOLOGIES[config['technology']]
        if technology not in d['selected']:
            b.click('button', technology)
            d = b.wait(lambda s: s['dialog'] and technology in s['dialog']['selected'] and
                       s['dialog']['fields'].get('Material') and s['dialog']['fields'],
                       'process options', stable=1)['dialog']
        checkpoint()
        material = config.get('material') or d['fields']['Material']['selected'][0]
        available = [x['label'] for x in d['fields']['Material']['options'] if not x['disabled']]
        if material not in available:
            raise RuntimeError(f'{material} is not offered for {config["technology"]}')
        if material not in d['selected']:
            b.click('button', material)
            d = b.wait(lambda s: s['dialog'] and material in s['dialog']['selected'] and s['dialog']['fields'],
                       'material options', stable=1)['dialog']
        checkpoint()
        if config.get('color') and config['color'] not in d['selected']:
            b.click('button', config['color'])
        if not any(i['role'] == 'spinbutton' and i['value'] == str(config['quantity']) for i in d['inputs']):
            b.snapshot()
            b.call('fill', '[role=dialog] input[role=spinbutton]', str(config['quantity']))
            b.call('press', 'Tab')
        d = b.wait(lambda s: s['dialog'] and not s['loading'] and
                   (s['dialog']['text'], str(s['dialog']['inputs'])), 'updated specifications', stable=2)['dialog']
        checkpoint()
        fields = d['fields']
        observed = {**config, 'material': material,
                    'color': (fields.get('Color', {}).get('selected') or [None])[0]}
        warnings = [line.strip() for line in d['text'].splitlines() if INVALID.search(line)]
        return {'observed': observed, 'options': fields, 'warnings': warnings, 'configuration': d}

    def save_quote(self, config, progress, checkpoint):
        b = self.browser
        b.checkpoint = checkpoint
        d = self.dialog()
        checkpoint()
        progress('quoting', 'Saving your settings and checking the price')
        # Set the category and description only when they differ from the saved form.
        if self.saved_category != config['category'] or not any(i['value'] == config['description'] for i in d['inputs']):
            b.snapshot()
            b.call('click', '(//*[@role="dialog"]//input[@placeholder="Select"])[last()]')
            b.click('menuitem', CATEGORIES[config['category']])
            b.click('menuitem', 'others')
            b.call('fill', b.ref('textbox', 'Enter a clear description'), config['description'])
        d = b.state()['dialog']
        if not any(i['value'] == config['description'] for i in d['inputs']):
            raise RuntimeError('The product description was changed or truncated by JLC3DP')
        checkpoint()
        b.click('button', 'Save')
        b.wait(lambda s: s['dialog'] is None, 'saved settings', timeout=20)
        state = b.wait(lambda s: stable_quote(s, self.file.name, config['quantity']), 'updated quote', stable=2)
        checkpoint()
        progress('verifying', 'Verifying the saved material, color, and quantity')
        saved = self.dialog()
        for value in (TECHNOLOGIES[config['technology']], config['material'], config.get('color')):
            if value and value not in saved['selected']:
                raise RuntimeError(f'Saved settings do not match {value}')
        if not any(i['role'] == 'spinbutton' and i['value'] == str(config['quantity']) for i in saved['inputs']):
            raise RuntimeError('Saved quantity does not match the request')
        if not any(i['value'] == config['description'] for i in saved['inputs']):
            raise RuntimeError('Saved description does not match the request')
        self.saved_category = config['category']
        b.click('button', 'Close')
        checkpoint()
        quote = self.quote_data(state, config)
        # Shipping is published only after its own wait, not copied from an older configuration.
        quote['shipping'] = None
        quote['shipping_status'] = 'pending'
        quote['estimated_total'] = None
        return quote

    def shipping(self, config, progress, checkpoint):
        self.browser.checkpoint = checkpoint
        progress('shipping', 'Checking the US shipping estimate')
        try:
            state = self.browser.wait(lambda s: stable_quote(s, self.file.name, config['quantity'], True),
                                      'shipping estimate', timeout=20, stable=3)
        except RuntimeError as exc:
            if not str(exc).startswith('Timed out'):
                raise
            state = self.browser.wait(lambda s: stable_quote(s, self.file.name, config['quantity']),
                                      'manufacturing estimate', stable=1)
        checkpoint()
        return self.quote_data(state, config)

    def quote_data(self, state, config, baseline=False):
        text = state['text']
        _, total, shipping = prices(state)
        dimensions = re.search(r'([\d.]+)×([\d.]+)×([\d.]+) cm', text)
        build = re.search(r'Build Time\s*(.*?)\n\s*\*', text, re.S)
        ship_text = text.split('Shipping Estimate', 1)[-1].split('Coupons', 1)[0].strip()
        return {
            'config': config, 'baseline': baseline, 'currency': 'USD',
            'manufacturing': str(total), 'shipping': str(shipping) if shipping is not None else None,
            'shipping_status': 'estimated' if shipping is not None else 'unavailable',
            'estimated_total': str(total + shipping) if shipping is not None else None,
            'shipping_details': ship_text, 'country': 'United States',
            'build_time': build.group(1).strip() if build else None,
            'dimensions_mm': [float(x) * 10 for x in dimensions.groups()] if dimensions else None,
            'source_url': URL,
        }
