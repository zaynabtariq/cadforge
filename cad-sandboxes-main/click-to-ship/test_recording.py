"""Recording completion, safe failure reporting, and credential isolation."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from browserbase_capture import capture, load_credentials


class RecordingTests(unittest.TestCase):
    def test_archives_completed_video_without_persisting_signed_urls(self):
        updates = []
        with tempfile.TemporaryDirectory() as directory:
            with patch('browserbase_capture.request', side_effect=[{}, {'downloads': [
                {'pageId': '0', 'status': 'COMPLETED', 'downloadUrl': 'https://example.com/clip?token=secret'}]}]), \
                    patch('browserbase_capture.urlopen', return_value=io.BytesIO(b'video-data')):
                capture('session', directory, lambda **patch: updates.append(patch))
            self.assertEqual((Path(directory) / '0.mp4').read_bytes(), b'video-data')
            metadata = (Path(directory) / 'recording.json').read_text()
            self.assertNotIn('secret', metadata)
            self.assertEqual(json.loads(metadata)['pages'][0]['bytes'], 10)
            self.assertEqual(updates[-1]['status'], 'ready')

    def test_download_errors_do_not_expose_signed_urls(self):
        updates = []
        with tempfile.TemporaryDirectory() as directory:
            with patch('browserbase_capture.request', side_effect=[{}, {'downloads': [
                {'pageId': '0', 'status': 'COMPLETED', 'downloadUrl': 'https://example.com/clip?token=secret'}]}]), \
                    patch('browserbase_capture.urlopen', side_effect=OSError('https://example.com/?token=secret')):
                capture('session', directory, lambda **patch: updates.append(patch))
            self.assertEqual(updates[-1]['status'], 'error')
            self.assertNotIn('secret', str(updates))
            self.assertFalse((Path(directory) / 'recording.json').exists())

    def test_loads_only_browserbase_credentials_and_preserves_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'BROWSERBASE_API_KEY': 'existing'}, clear=True):
            file = Path(directory) / 'test.env'
            file.write_text('BROWSERBASE_API_KEY="from-file"\nBROWSERBASE_PROJECT_ID=project\nAWS_SECRET_ACCESS_KEY=private\n')
            load_credentials(file)
            self.assertEqual(os.environ['BROWSERBASE_API_KEY'], 'existing')
            self.assertEqual(os.environ['BROWSERBASE_PROJECT_ID'], 'project')
            self.assertNotIn('AWS_SECRET_ACCESS_KEY', os.environ)


if __name__ == '__main__':
    unittest.main()
