import struct
import tempfile
import unittest
from pathlib import Path

import core
from dlbin_codec import DLBin, blocks, content_hash


class DataFileTests(unittest.TestCase):
    def sample(self):
        header = lambda: b"LDLD\x01\0\0\0" + struct.pack("<IIQ", 123, 8, 1)
        plain = b"prefix00" + header() + struct.pack("<fI", 1.0, 25) + header() + struct.pack("<fI", 2.0, 35)
        return DLBin("sample.dl_bin", core.seal(plain))

    def test_decode_and_no_change_roundtrip(self):
        data = self.sample()
        self.assertEqual(len(data.resources), 2)
        self.assertEqual(data.payload(0, 0), struct.pack("<fI", 1.0, 25))
        self.assertEqual(data.prepare(), (data.sealed, []))

    def test_rejects_length_change(self):
        with self.assertRaises(ValueError):
            self.sample().replace(0, 0, b"too short")

    def test_edited_file_is_sealed_and_hash_preserved(self):
        data = self.sample()
        original = data.sealed
        requested = struct.pack("<fI", 1.25, 25)
        data.replace(0, 0, requested)
        sealed, adjustments = data.prepare()
        result = DLBin("edited.dl_bin", sealed)
        self.assertEqual(result.payload(0, 0), requested)
        self.assertEqual(adjustments, [])
        self.assertEqual(content_hash(result.plain), content_hash(data.plain))
        self.assertEqual(result.headers, data.headers)
        self.assertEqual(data.sealed, original)
        self.assertEqual(result.payload(1, 0), data.payload(1, 0))

    def test_export_reopen_and_protect_source(self):
        data = self.sample()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            target = Path(folder) / "sample.dl_bin"
            data.save(target, data.sealed)
            result = DLBin.open(target)
            self.assertEqual(result.plain, data.plain)
            with self.assertRaises(ValueError):
                result.save(target, data.sealed)

    def test_restore_removes_replacement(self):
        data = self.sample()
        original = data.payload(0, 0)
        data.replace(0, 0, b"x" * len(original))
        data.replace(0, 0, original)
        self.assertEqual(data.replacements, {})

    def test_raw_edits_are_not_guessed_to_be_floats(self):
        header = b"LDLD\x01\0\0\0" + struct.pack("<IIQ", 123, 8, 1)
        data = DLBin("single.dl_bin", core.seal(b"abcd" + header + struct.pack("<fI", 1.0, 25)))
        data.replace(0, 0, struct.pack("<fI", 1.25, 25))
        self.assertEqual(data.float_edits[0], set())
        with self.assertRaisesRegex(ValueError, "Hash correction"):
            data.prepare()

    def test_explicit_float_tracking_removed_by_raw_change(self):
        data = self.sample()
        data.replace(0, 0, struct.pack("<fI", 1.25, 25), float_offsets=[0])
        self.assertEqual(data.float_edits[0], {0})
        data.replace(0, 0, struct.pack("<fI", 1.5, 25))
        self.assertEqual(data.float_edits[0], set())

    def test_invalid_structure_and_ciphertext_rejected(self):
        with self.assertRaises(ValueError):
            blocks(b"not an LDLD file")
        with self.assertRaises(ValueError):
            DLBin("bad.dl_bin", core.seal(b"LDLD\x01\0\0\0" + struct.pack("<IIQ", 1, 1000, 1)))
        with self.assertRaises(ValueError):
            DLBin("bad.dl_bin", b"x" * 100)


if __name__ == "__main__":
    unittest.main()
