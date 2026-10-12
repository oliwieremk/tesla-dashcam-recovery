import json
from pathlib import Path
import re
import tempfile
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

from teslarecover import server
from teslarecover.localize import CATALOG, localize_quality, phase, translate


class Markers(HTMLParser):
    def __init__(self): super().__init__(); self.keys=[]
    def handle_starttag(self, tag, attrs):
        self.keys.extend(value for key, value in attrs if key.startswith('data-i18n'))


class LanguageTests(unittest.TestCase):
    def test_static_labels_and_dynamic_placeholders_have_english_translations(self):
        root = Path(__file__).resolve().parent.parent / 'teslarecover' / 'static'
        parser = Markers(); parser.feed((root / 'index.html').read_text())
        for key in parser.keys:
            self.assertIn(key, CATALOG)
        for key, english in CATALOG.items():
            self.assertEqual(sorted(re.findall(r'\{\d+\}', key)), sorted(re.findall(r'\{\d+\}', english)), key)
        self.assertEqual(translate('Wybrano: {0} · {1} po usunięciu · {2}', 'en', ['2 clips', 1, '1 GB']),
                         'Selected: 2 clips · 1 from deleted data · 1 GB')

    def test_preference_persists_and_does_not_reset_scan_or_job(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'settings.json')
            job = server.Job('scan', lambda job: None)
            job.progress('Copying deleted clip 23', 5, 10)
            scan = {'clips': [{'id': '23'}]}
            with patch.object(server, 'SETTINGS', path), patch.object(server.state, 'settings', {'out_dir': '/tmp/recovered'}), \
                    patch.object(server.state, 'window', None), patch.object(server.state, 'job', job), \
                    patch.object(server.state, 'scan', scan):
                server.set_language('en')
                self.assertEqual(server.get_state()['job']['phase'], 'Copying deleted clip 23')
                self.assertIs(server.state.scan, scan)
                self.assertIs(server.state.job, job)
                self.assertEqual(json.loads(Path(path).read_text())['out_dir'], '/tmp/recovered')
                self.assertEqual(server.State().settings['language'], 'en')
                server.set_language('pl')
                self.assertEqual(server.get_state()['job']['phase'], 'Kopiuję usunięty klip 23')
                with self.assertRaises(server.HTTPException): server.set_language('fr')

    def test_quality_and_common_error_descriptions_are_bilingual(self):
        clip = {'status': 'ok', 'repaired': True, 'repaired_seconds': 32.5}
        self.assertEqual(localize_quality(clip, 'pl')['label'], 'Naprawione')
        english = localize_quality(clip, 'en')
        self.assertEqual(english['label'], 'Repaired')
        self.assertIn('32.5 seconds', english['note'])
        self.assertEqual(localize_quality({'truncated': True}, 'en')['code'], 'partial')
        self.assertEqual(phase('Getting keys from Tesla', 'en'), 'Getting keys from Tesla')
        self.assertEqual(phase('Czekam na zgodę macOS na odczyt USB', 'en'), 'Waiting for macOS authorization to read the USB')
        self.assertIn('cannot', translate('Nie można zmieniać nagrań bezpośrednio na nośniku Tesli.', 'en'))


if __name__ == '__main__': unittest.main()
