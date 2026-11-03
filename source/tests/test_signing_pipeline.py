"""Check release integrity across signing and diagnostic packaging."""
from pathlib import Path
import hashlib
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import signing_pipeline as pipeline
import build_ci_runtime


def pe():
    data = bytearray(512)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 88, 0x10b)
    data[400:405] = b'code!'
    return bytes(data)


def signed_pe():
    data = bytearray(pe())
    struct.pack_into('<I', data, 88 + 64, 123)
    struct.pack_into('<II', data, 88 + 96 + 32, 512, 16)
    data.extend(b'certificate-data')
    return bytes(data)


class SigningTests(unittest.TestCase):
    def test_signature_only_edits_accepted_code_edits_rejected(self):
        self.assertEqual(pipeline.unsigned_content(pe()), pipeline.unsigned_content(signed_pe()))
        tampered = bytearray(signed_pe())
        tampered[400] ^= 1
        self.assertNotEqual(pipeline.unsigned_content(pe()), pipeline.unsigned_content(tampered))

    def test_repack_preserves_docs_and_updates_exe_and_archive_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package, signed, out = root/'unsigned.zip', root/'signed.exe', root/'signed.zip'
            signed.write_bytes(signed_pe())
            with zipfile.ZipFile(package, 'w') as z:
                z.writestr(pipeline.build_release.LEGACY_EXE_PATH, pe())
                z.writestr('ModDiver Laboratory/README.md', b'doc')
                z.writestr('ModDiver Laboratory/SHA256SUMS.txt', b'old hashes')
            original = package.read_bytes()
            pipeline.finish(package, signed, out)
            self.assertEqual(package.read_bytes(), original)
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.read(pipeline.build_release.LEGACY_EXE_PATH), signed_pe())
                self.assertEqual(z.read('ModDiver Laboratory/README.md'), b'doc')
                hashes = z.read('ModDiver Laboratory/SHA256SUMS.txt').decode()
                self.assertIn(hashlib.sha256(signed_pe()).hexdigest()+'  ModDiver Laboratory.exe', hashes)
            self.assertIn(hashlib.sha256(out.read_bytes()).hexdigest(), out.with_suffix('.zip.sha256').read_text())
            tampered = bytearray(signed_pe())
            tampered[400] ^= 1
            signed.write_bytes(tampered)
            with self.assertRaises(ValueError):
                pipeline.finish(package, signed, root/'bad.zip')

    def test_runtime_preserves_binaries_and_license_excludes_site_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prefix = root/'python'
            files = {'python.exe': b'python', 'pythonw.exe': b'gui', 'LICENSE.txt': b'license',
                     'Lib/encodings/__init__.py': b'encoding', 'DLLs/_tkinter.pyd': b'tk',
                     'tcl/tcl8.6/init.tcl': b'tcl', 'Lib/site-packages/foreign.py': b'omit'}
            for name, data in files.items():
                path = prefix/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            out = root/'runtime.zip'
            build_ci_runtime.build(prefix, out)
            with zipfile.ZipFile(out) as z:
                self.assertNotIn('Lib/site-packages/foreign.py', z.namelist())
                self.assertEqual(z.read('pythonw.exe'), files['pythonw.exe'])
                self.assertEqual(z.read('LICENSE.txt'), b'license')


if __name__ == '__main__':
    unittest.main()
