import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import core
from archive_codec import Archive, LUA_TYPE, MAGIC
from dlbin_codec import DLBin, content_hash
from mod_repair import analyse, match_block, normalized_mod, snapshot, transplant, stratagem_flags
from portable_hash import finish_tail
import repair_reference


class ExtendedRepairTests(unittest.TestCase):
    def stratagem_schema(self):
        member = lambda atom, storage, offset, size: SimpleNamespace(atom=atom, storage=storage, offset=offset, size=size)
        array = member(1, 20, 0, 16)
        array.type_id = 42
        return SimpleNamespace(types={
            0x30EB6399: SimpleNamespace(name='StratagemSettings', size=16, members=[array]),
            42: SimpleNamespace(name='StratagemInfo', size=400, members=[member(0, 6, 4, 4),
                member(3, 4, 368, 1), member(3, 4, 368, 1)])})

    def stratagem_array(self, rows):
        data = bytearray(struct.pack('<QQ', 16, len(rows)) + bytes(400*len(rows)))
        for index, (identity, flags) in enumerate(rows):
            struct.pack_into('<I', data, 16+index*400+4, identity)
            data[16+index*400+368] = flags
        return bytes(data)

    def test_schema_flags_follow_ids_and_preserve_other_game_bits(self):
        old = self.stratagem_array([(10, 2), (20, 2)])
        mod = self.stratagem_array([(10, 0), (20, 2)])
        new = self.stratagem_array([(20, 6), (10, 10)])
        with patch('game_schema.Library.open', return_value=self.stratagem_schema()):
            repaired, report = stratagem_flags(old, new, mod, 'schema')
        expected = self.stratagem_array([(20, 6), (10, 8)])
        self.assertEqual(repaired, expected)
        self.assertEqual(len(report), 1)

    def test_schema_flags_reject_unrelated_edits_removed_ids_and_layouts(self):
        old = self.stratagem_array([(10, 2)])
        mod = bytearray(self.stratagem_array([(10, 0)]))
        mod[30] = 7
        with patch('game_schema.Library.open', return_value=self.stratagem_schema()):
            with self.assertRaisesRegex(ValueError, 'outside'):
                stratagem_flags(old, old, mod, 'schema')
            with self.assertRaisesRegex(ValueError, 'removed'):
                stratagem_flags(old, self.stratagem_array([(20, 2)]), self.stratagem_array([(10, 0)]), 'schema')
        schema = self.stratagem_schema()
        schema.types[42].size = 408
        with patch('game_schema.Library.open', return_value=schema):
            with self.assertRaisesRegex(ValueError, 'verified'):
                stratagem_flags(old, old, old, 'schema')

    def data(self, path, payloads):
        plain = b'prefix00'
        for payload in payloads:
            plain += b'LDLD\x01\0\0\0' + struct.pack('<IIQ', 123, len(payload), 1) + payload
        return DLBin(path, core.seal(plain))

    def test_repeated_types_reorder_and_footer_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            a, b = [bytes((i*13+seed) % 256 for i in range(128)) for seed in (1, 7)]
            old = self.data('sample.dl_bin', (a, b))
            candidate = bytearray(old.plain)
            start = old.resources[0].offsets[0]
            candidate[start+64:start+68] = b'MOD!'
            mod = DLBin('sample.dl_bin', core.seal(finish_tail(old.plain, candidate, old.headers)))
            new = self.data('sample.dl_bin', (b, b'inserted' + a))
            paths = []
            for label, obj in (('old', old), ('new', new), ('mod', mod)):
                path = root / label / 'sample.dl_bin'
                path.parent.mkdir()
                path.write_bytes(obj.sealed)
                paths.append(path)
            saved = snapshot([paths[0]], root)
            plan = analyse(saved / 'sample.dl_bin', paths[1], paths[2])
            self.assertEqual(plan.errors, [])
            output = root / 'out'
            output.mkdir()
            result = DLBin.open(plan.export(output)[0])
            self.assertEqual(result.payload(0, 0), b)
            self.assertEqual(result.payload(1, 0), b'inserted' + a[:64] + b'MOD!' + a[68:])
            self.assertEqual(content_hash(result.plain), content_hash(new.plain))

    def test_arbitrary_extension_and_tampered_footer_rejected(self):
        old = self.data('sample.dl_bin', (bytes(range(96)),))
        tail = bytearray(finish_tail(old.plain, old.plain, old.headers))
        tail[-1] ^= 1
        mod = DLBin('sample.dl_bin', core.seal(bytes(tail)))
        with self.assertRaisesRegex(ValueError, 'canonical'):
            normalized_mod(old, mod)
        expanded = self.data('sample.dl_bin', (bytes(range(96)) + b'not a footer',))
        with self.assertRaises(ValueError):
            normalized_mod(old, expanded)

    def test_identical_repeated_blocks_do_not_guess(self):
        data = self.data('sample.dl_bin', (bytes(range(128)), bytes(range(128))))
        with self.assertRaisesRegex(ValueError, 'unique identity'):
            match_block(data, data.resources[0], bytes(range(64)) + b'MOD!' + bytes(range(68, 128)))

    def test_clustered_edits_survive_unrelated_nearby_update(self):
        old = bytes(range(128))
        mod = old[:40] + b'12345678' + old[48:]
        new = b'inserted' + old[:80] + b'GAME' + old[84:]
        repaired, report = transplant(old, new, mod)
        self.assertEqual(repaired[48:56], b'12345678')
        self.assertEqual(repaired[88:92], b'GAME')
        self.assertEqual(len(report), 1)

    def test_reference_wrapper_inspection_executes_no_code(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            data = self.data('generated_test.dl_bin', (bytes(range(128)),)).sealed
            meta = f'target=data/game/generated_test.dl_bin\nsize={len(data)}'.encode()
            wrapper = b'HD2FM1' + struct.pack('<I', len(meta)) + meta + data
            payload = struct.pack('<II', len(wrapper), 2) + wrapper
            header = struct.pack('<III', MAGIC, 1, 1) + bytes(60)
            types = struct.pack('<QQQII', 0, LUA_TYPE, 1, 16, 16)
            row = struct.pack('<7Q6I', 1, LUA_TYPE, 184, 0, 0, 0, 0, len(payload), 0, 0, 16, 16, 0)
            reference = root / 'fixed.zip'
            original = root / 'old.zip'
            with zipfile.ZipFile(reference, 'w') as archive:
                archive.writestr('Install/0123456789abcdef.patch_0', header + types + row + payload)
                archive.writestr('evil.py', 'raise RuntimeError("Do not execute")')
            with zipfile.ZipFile(original, 'w') as archive:
                archive.writestr('data/game/generated_test.dl_bin', data)
            report = repair_reference.compare(reference, original)
            self.assertIn('Identical sealed gameplay', report[0]['comparison'])


if __name__ == '__main__':
    unittest.main()
