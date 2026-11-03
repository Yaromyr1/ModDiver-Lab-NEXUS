"""Legacy installation reads and atomic multi-selection volume edits."""
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_backend import AudioBackend, configure


class AudioCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = tempfile.TemporaryDirectory()
        cls.old_cache = os.environ.get('audioStudio_CACHE')
        cls.Session = configure(cls.cache.name)

    @classmethod
    def tearDownClass(cls):
        cls.cache.cleanup()
        if cls.old_cache is None:
            os.environ.pop('audioStudio_CACHE', None)
        else:
            os.environ['audioStudio_CACHE'] = cls.old_cache

    def archive(self, folder, name='0123456789abcdef'):
        from audioStudio.game import PATCH_MAGIC, WWISE_STREAM
        # One resource with bytes in both the TOC file and its raw stream sidecar.
        head = struct.pack('<III', PATCH_MAGIC, 1, 1) + bytes(60)
        entry = bytearray(80)
        struct.pack_into('<QQQQ', entry, 0, 123, WWISE_STREAM, 184, 3)
        struct.pack_into('<II', entry, 56, 4, 5)
        archive = folder / name
        archive.write_bytes(head + bytes(32) + entry + b'bank')
        Path(str(archive) + '.stream').write_bytes(b'---sound!')
        return archive

    def test_hellforge_root_and_legacy_resource_reads(self):
        from audioStudio.game import Game, data_folder, WWISE_STREAM
        from audioStudio._vendor import slim
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / 'game' / 'data'
            data.mkdir(parents=True)
            archive = self.archive(data)
            self.assertEqual(data_folder(root), data)
            self.assertEqual(data_folder(root / 'game'), data)
            self.assertEqual(data_folder(data), data)
            # A preceding Steam scan must not leak bundle packages into this scan.
            with patch.object(slim, 'package_contents', {'stale': object()}), patch.object(slim, 'bundle_offsets', {}):
                game = Game(data)
                self.assertEqual(game.packages, [archive.name])
                self.assertEqual(game.resource(archive.name, 123, WWISE_STREAM), (b'bank', b'sound'))
                self.assertEqual(game.stream_head(archive.name, 123, 2), b'so')
                self.assertEqual(game.stream(archive.name), b'---sound!')
                before = game.audio_fingerprint
                Path(str(archive) + '.stream').write_bytes(b'---changed!')
                self.assertNotEqual(Game(data).audio_fingerprint, before)

    def test_dsar_and_raw_range_reads_match(self):
        from audioStudio.game import archive_read
        with tempfile.TemporaryDirectory() as temp:
            data = b'0123456789'
            raw, dsar = Path(temp) / 'raw', Path(temp) / 'compressed'
            raw.write_bytes(data)
            head = bytearray(32)
            head[:4] = b'DSAR'
            struct.pack_into('<I', head, 8, 1)
            chunk = struct.pack('<QQIIB7x', 0, 64, len(data), len(data), 0)
            dsar.write_bytes(head + chunk + data)
            for file in (raw, dsar):
                self.assertEqual(archive_read(file), data)
                self.assertEqual(archive_read(file, 2, 4), b'2345')
                self.assertEqual(archive_read(file, 8, 10), b'89')

    def test_bulk_gain_is_one_undo_step_and_preserves_timing(self):
        from audioStudio.project import Project, Replacement
        with tempfile.TemporaryDirectory() as temp:
            session = self.Session(load=False)
            session.project = Project(name='Bulk', path=Path(temp) / 'test.audi', library=[])
            session.project.replacements = [Replacement(target=2, audio='clip.wav', fit_timing=False)]
            session.project.gains = {1: -2, 2: -4, 3: 9}
            backend = AudioBackend.__new__(AudioBackend)
            backend.session = session
            # File probing and game catalogue are unrelated to this transaction.
            with patch.object(session, '_tidy_cues'), patch.object(session, '_cover'), patch.object(session, 'project_state', return_value={}):
                backend.edit_volume_many(['1', '2', '1'], '6')
                self.assertEqual(session.project.gains, {1: 6, 3: 9})
                self.assertEqual(session.project.replacements[0].gain_db, 6)
                self.assertFalse(session.project.replacements[0].fit_timing)
                self.assertEqual(len(session.undo_stack), 1)
                session.undo()
                self.assertEqual(session.project.gains, {1: -2, 2: -4, 3: 9})
                session.redo()
                self.assertEqual(session.project.gains, {1: 6, 3: 9})
                backend.edit_volume_many(['1', '2'], 0)
                self.assertEqual(session.project.gains, {3: 9})
                self.assertEqual(session.project.replacements[0].gain_db, 0)
                before = session.project.to_json()
                for gain in ('nan', 'inf', '-97', 'bad'):
                    with self.assertRaises(ValueError):
                        backend.edit_volume_many(['1', '2'], gain)
                with self.assertRaises(Exception):
                    backend.edit_volume_many(['1', 'not an ID'], 3)
                self.assertEqual(session.project.to_json(), before)


if __name__ == '__main__':
    unittest.main()
