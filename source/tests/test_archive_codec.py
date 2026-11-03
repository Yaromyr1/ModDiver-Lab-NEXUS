import struct
import tempfile
import unittest
from pathlib import Path

from archive_codec import Archive, LUA_TYPE, lua_source


class ArchiveTests(unittest.TestCase):
    def sample(self):
        # Keep nonzero opaque metadata to ensure repacking preserves unknown fields.
        header = struct.pack("<III", 0xF0000011, 1, 2) + b"M" * 60
        types = struct.pack("<QQQII", 0, LUA_TYPE, 2, 16, 16)
        main_offset = 72 + 32 + 160
        rows = struct.pack("<7Q6I", 1, LUA_TYPE, main_offset, 2, 3, 7, 9, 3, 4, 3, 16, 16, 0)
        rows += struct.pack("<7Q6I", 2, LUA_TYPE, main_offset + 3, 0, 0, 11, 13, 3, 0, 0, 16, 16, 1)
        return Archive("original.patch_0", (header + types + rows + b"ABCDEF", b"xxSTRMtail", b"xxxGPUtail"))

    def test_unchanged_is_byte_identical(self):
        archive = self.sample()
        self.assertEqual(archive.rebuild(), archive.blobs)

    def test_resize_all_sections_and_preserve_other_resources(self):
        archive = self.sample()
        for section in range(3):
            archive.replace(0, section, b"replacement" * (section + 1))
        blobs = archive.rebuild()
        result = Archive("output.patch_0", blobs)
        for section in range(3):
            self.assertEqual(result.payload(0, section), b"replacement" * (section + 1))
        self.assertEqual(result.payload(1, 0), b"DEF")
        self.assertEqual(blobs[0][:104], archive.blobs[0][:104])
        self.assertEqual(blobs[0][144:160], archive.blobs[0][144:160])

    def test_empty_replacement(self):
        archive = self.sample()
        archive.replace(0, 1, b"")
        result = Archive("out", archive.rebuild())
        self.assertEqual(result.payload(0, 1), b"")

    def test_restoring_bytes_removes_staged_change(self):
        archive = self.sample()
        original = archive.payload(0, 0)
        archive.replace(0, 0, b"new")
        archive.replace(0, 0, original)
        self.assertEqual(archive.replacements, {})

    def test_rejects_bad_bounds_and_header(self):
        original = self.sample()
        damaged = bytearray(original.blobs[0])
        struct.pack_into("<Q", damaged, 104 + 16, len(damaged) + 10)
        with self.assertRaises(ValueError):
            Archive("bad", (bytes(damaged), *original.blobs[1:]))
        with self.assertRaises(ValueError):
            Archive("bad", (b"BAD" * 100, b"", b""))
        with self.assertRaises(ValueError):
            Archive("bad", (original.blobs[0][:120], b"", b""))

    def test_missing_required_sidecar_rejected(self):
        archive = self.sample()
        with self.assertRaises(ValueError):
            Archive("missing", (archive.blobs[0], b"", b""))

    def test_export_and_reopen_triplet(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            archive = self.sample()
            archive.replace(0, 2, b"new gpu bytes")
            target = Path(folder) / "export.patch_0"
            archive.export(target)
            self.assertEqual(Archive.open(target).payload(0, 2), b"new gpu bytes")
            with self.assertRaises(ValueError):
                Archive.open(target).export(target)

    def test_bundled_chef_roundtrip_and_lua_edit(self):
        path = Path(__file__).resolve().parents[1] / "builtin" / "chef_loader" / "9ba626afa44a3aa3.patch_0"
        archive = Archive.open(path)
        self.assertEqual(archive.rebuild(), archive.blobs)
        resource = next(r for r in archive.resources if r.type_hash == LUA_TYPE)
        original = archive.payload(resource.index, 0)
        self.assertIsNotNone(lua_source(original))
        source = (lua_source(original) + "\n-- decoder roundtrip\n").encode("utf-8")
        edited = struct.pack("<II", len(source), 2) + source
        archive.replace(resource.index, 0, edited)
        result = Archive("edited", archive.rebuild())
        self.assertEqual(result.payload(resource.index, 0), edited)
        for other in archive.resources:
            if other.index != resource.index:
                for section in range(3):
                    self.assertEqual(result.payload(other.index, section), archive.payload(other.index, section))


if __name__ == "__main__":
    unittest.main()
