"""Concurrency contracts: no stale publication, duplicate work, or cross-session state."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from server import QuoteSession, Conflict


class FakeAdapter:
    def __init__(self, session_id, file):
        self.started = threading.Event()
        self.release = threading.Event()
        self.inspected = []
        self.saved = []

    def bootstrap(self, progress, checkpoint):
        return {'config': {'quantity': 1}, 'manufacturing': '1.00'}

    def inspect(self, config, progress, checkpoint):
        quantity = config['quantity']
        self.inspected.append(quantity)
        if quantity == 2:
            self.started.set()
            self.release.wait(5)
            checkpoint()
        if quantity == 9:
            return {'observed': config, 'options': {}, 'warnings': ['Too large for this material']}
        return {'observed': config, 'options': {}, 'warnings': []}

    def save_quote(self, config, progress, checkpoint):
        self.saved.append(config['quantity'])
        return {'config': config, 'manufacturing': str(config['quantity'])}

    def shipping(self, config, progress, checkpoint):
        return self.save_quote(config, progress, checkpoint)

    def close(self):
        pass


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        file = Path(self.temp.name) / 'test.stl'
        file.write_text('test')
        self.session = QuoteSession('test', file, FakeAdapter)
        self.session.start()
        self.wait(lambda: self.session.bootstrapped)

    def tearDown(self):
        self.session.adapter.release.set()
        self.session.close()
        self.session.thread.join(5)
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('worker did not reach expected state')

    def config(self, quantity):
        return {'technology': 'SLA', 'material': '9600 Resin', 'color': 'White',
                'quantity': quantity, 'category': 'blocks', 'description': 'Test cube'}

    def test_latest_request_wins_and_pending_requests_coalesce(self):
        self.session.submit('two', 0, 'quote', self.config(2))
        self.assertTrue(self.session.adapter.started.wait(2))
        self.session.submit('three', 1, 'quote', self.config(3))
        self.session.submit('four', 2, 'quote', self.config(4))
        self.session.adapter.release.set()
        self.wait(lambda: self.session.snapshot()['quote'].get('revision') == 3)
        self.assertNotIn(2, self.session.adapter.saved)
        self.assertNotIn(3, self.session.adapter.inspected)
        self.assertEqual(self.session.snapshot()['quote']['config']['quantity'], 4)
        self.assertFalse(any(e['event'] == 'quote_ready' and e['revision'] < 3 for e in self.session.events))

    def test_idempotency_and_stale_client_conflict(self):
        first = self.session.submit('same', 0, 'inspect', self.config(2))
        duplicate = self.session.submit('same', 0, 'inspect', self.config(2))
        self.assertEqual(first['accepted_revision'], duplicate['accepted_revision'])
        self.assertTrue(duplicate['duplicate'])
        with self.assertRaises(Conflict):
            self.session.submit('different', 0, 'quote', self.config(3))
        with self.assertRaises(Conflict):
            self.session.submit('same', 1, 'quote', self.config(4))

    def test_incompatible_selection_keeps_previous_quote_and_can_recover(self):
        self.session.submit('bad', 0, 'quote', self.config(9))
        self.wait(lambda: self.session.snapshot()['phase'] == 'blocked')
        self.assertEqual(self.session.snapshot()['quote']['revision'], 0)
        self.assertEqual(self.session.snapshot()['options_revision'], 1)
        self.session.submit('good', 1, 'quote', self.config(4))
        self.wait(lambda: self.session.snapshot()['quote'].get('revision') == 2)
        self.assertIsNone(self.session.snapshot()['error'])

    def test_snapshot_is_detached_and_event_sequence_is_monotonic(self):
        snapshot = self.session.snapshot()
        snapshot['desired']['quantity'] = 800
        self.assertEqual(self.session.snapshot()['desired']['quantity'], 1)
        sequence = [e['seq'] for e in self.session.events]
        self.assertEqual(sequence, sorted(set(sequence)))

    def test_early_choices_do_not_cancel_upload_and_latest_choice_is_quoted(self):
        class SlowUpload(FakeAdapter):
            def __init__(self, *args):
                super().__init__(*args)
                self.upload_started = threading.Event()
                self.upload_release = threading.Event()

            def bootstrap(self, progress, checkpoint):
                self.upload_started.set()
                self.upload_release.wait(3)
                checkpoint()
                return super().bootstrap(progress, checkpoint)

        directory = Path(self.temp.name) / 'early'
        directory.mkdir()
        file = directory / 'cube.stl'
        file.write_text('test')
        session = QuoteSession('early', file, SlowUpload)
        session.start()
        try:
            self.assertTrue(session.adapter.upload_started.wait(1))
            session.submit('early-two', 0, 'inspect', self.config(2))
            session.submit('early-four', 1, 'quote', self.config(4))
            self.assertFalse(session.snapshot()['bootstrapped'])
            session.adapter.upload_release.set()
            self.wait(lambda: session.snapshot()['phase'] == 'ready' and
                      (session.snapshot()['quote'] or {}).get('revision') == 2)
            initial = next(e for e in session.events if e['event'] == 'initial_estimate')
            self.assertEqual(initial['revision'], 2)
            self.assertEqual(initial['quote']['revision'], 0)
            self.assertEqual(session.snapshot()['quote']['config']['quantity'], 4)
            self.assertNotIn(2, session.adapter.inspected)
        finally:
            session.adapter.upload_release.set()
            session.close()
            session.thread.join(5)


if __name__ == '__main__':
    unittest.main()
