import struct
import tempfile
import unittest
from pathlib import Path

import core
from archive_codec import Archive, MAGIC
from dlbin_codec import DLBin, content_hash
from mod_repair import analyse, snapshot, transplant, verify_snapshot


class RepairTests(unittest.TestCase):
    def test_move_and_preserve_update(self):
        old = bytes(range(100))
        mod = old[:40] + b'MOD!' + old[44:]
        current = b'inserted' + old + b'new game data'
        repaired, report = transplant(old, current, mod)
        self.assertEqual(repaired, b'inserted' + mod + b'new game data')
        self.assertIn('0x28 -> 0x30', report[0])

    def test_ambiguous_signature_rejected(self):
        old = bytes(range(100))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            transplant(old, old + old, old[:40] + b'MOD!' + old[44:])

    def test_conflicting_game_change_rejected(self):
        old = bytes(range(100))
        with self.assertRaisesRegex(ValueError, 'same field'):
            transplant(old, old[:40] + b'GAME' + old[44:], old[:40] + b'MOD!' + old[44:])

    def test_resize_only_when_stock_unchanged(self):
        self.assertEqual(transplant(b'old', b'old', b'resized')[0], b'resized')
        with self.assertRaises(ValueError):
            transplant(b'old', b'new', b'resized')

    def test_dlbin_snapshot_relocation_export_current_hash(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            old, current, mod = [root / name / 'generated_test.dl_bin' for name in ('old', 'new', 'mod')]
            payload = bytes(range(100))
            # Explicit, valid second block.
            def write(path, data):
                path.parent.mkdir()
                header = lambda kind, size: b'LDLD\x01\0\0\0' + struct.pack('<IIQ', kind, size, 1)
                path.write_bytes(core.seal(b'prefix00' + header(123, len(data)) + data + header(456, 16) + b'X'*16))
            write(old, payload)
            write(current, b'inserted' + payload)
            write(mod, payload[:40] + b'MOD!' + payload[44:])
            saved = snapshot([old], root)
            plan = analyse(saved / old.name, current, mod)
            self.assertEqual(plan.errors, [])
            output = root / 'output'
            output.mkdir()
            exported = plan.export(output)
            result = DLBin.open(exported[0])
            self.assertEqual(result.payload(0, 0)[48:52], b'MOD!')
            self.assertEqual(content_hash(result.plain), content_hash(DLBin.open(current).plain))
            with self.assertRaisesRegex(ValueError, 'already exists'):
                plan.export(output)
            (saved / old.name).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                verify_snapshot(saved / old.name)

    def archive(self, path, name_hash, payload):
        header = struct.pack('<III', MAGIC, 1, 1) + bytes(60)
        types = struct.pack('<QQQII', 0, 22, 1, 16, 16)
        row = struct.pack('<7Q6I', name_hash, 22, 184, 0, 0, 0, 0, len(payload), 0, 0, 16, 16, 0)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(header + types + row + payload)

    def test_archive_hash_mapping_and_offsets_together(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            old, new, mod = [root / name / filename for name, filename in
                             (('old', 'abc'), ('new', 'abc'), ('mod', 'abc.patch_0'))]
            payload = bytes(range(100))
            self.archive(old, 1, payload)
            self.archive(new, 2, payload)
            self.archive(mod, 1, payload[:40] + b'MOD!' + payload[44:])
            saved = snapshot([old], root)
            plan = analyse(saved / old.name, new, mod)
            self.assertEqual(plan.errors, [])
            self.assertTrue(any('hash mapping' in line for line in plan.report))
            output = root / 'out'
            output.mkdir()
            result = Archive.open(plan.export(output)[0])
            self.assertEqual(result.resources[0].name_hash, 2)
            self.assertEqual(result.payload(0, 0)[40:44], b'MOD!')

    def test_no_proven_hash_mapping_blocks_all_export(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            old, new, mod = [root / name / 'abc' for name in ('old', 'new', 'mod')]
            self.archive(old, 1, bytes(range(100)))
            self.archive(new, 2, b'changed schema')
            self.archive(mod, 1, b'broken mod')
            saved = snapshot([old], root)
            plan = analyse(saved / old.name, new, mod)
            self.assertTrue(plan.errors)
            self.assertEqual(plan.current.replacements, {})
            with self.assertRaises(ValueError):
                plan.export(root / 'out')


if __name__ == '__main__':
    unittest.main()
