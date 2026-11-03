"""Tests for the app-package updater.

Run: python -m unittest discover -s tests -v
"""
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import updater  # noqa: E402


def make_package(version, inside=None, min_launcher=2, extra=None, meta_version=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("app.json", json.dumps({"version": meta_version or version, "min_launcher": min_launcher}))
        z.writestr("yao_forge.py", f'APP_NAME = "x"\nVERSION = "{inside or version}"\n')
        z.writestr("core.py", "print('core')\n")
        z.writestr("vendor/shodan/lua51.dll", b"\x00" * 64)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def release_for(package, version="1.8.9", sha=True, size=None):
    return {
        "version": version, "tag": "v" + version, "page_url": "https://github.com/x/y/releases/tag/v" + version,
        "asset_url": updater.DOWNLOAD_PREFIX + "v" + version + "/pkg.zip",
        "asset_size": len(package) if size is None else size,
        "sha256": hashlib.sha256(package).hexdigest() if sha else "",
    }


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data, True)
        self.app = self.data / "app"

    def install(self, package, release=None, api=2):
        release = release or release_for(package)
        with mock.patch.object(updater.urllib.request, "urlopen", lambda *a, **k: FakeResponse(package)):
            return updater.install_update(release, str(self.data), api)

    def test_happy_path_extracts_and_points_at_new_version(self):
        self.assertEqual(self.install(make_package("1.8.9")), "1.8.9")
        self.assertTrue((self.app / "1.8.9" / "yao_forge.py").is_file())
        self.assertTrue((self.app / "1.8.9" / "vendor" / "shodan" / "lua51.dll").is_file())
        self.assertTrue((self.app / "1.8.9" / updater.OK_MARKER).is_file())
        self.assertEqual(updater.read_pointer(self.app), ("1.8.9", None))
        self.assertEqual([p.name for p in self.app.iterdir() if p.name.startswith(".staging")], [])

    def test_pointer_keeps_previous_version_for_rollback(self):
        self.app.mkdir(parents=True)
        (self.app / "current.txt").write_text("1.8.8\n")
        self.install(make_package("1.8.9"))
        self.assertEqual(updater.read_pointer(self.app), ("1.8.9", "1.8.8"))
        self.install(make_package("1.8.10"), release_for(make_package("1.8.10"), "1.8.10"))
        self.assertEqual(updater.read_pointer(self.app), ("1.8.10", "1.8.9"))

    def test_stale_package_is_refused_and_nothing_changes(self):
        pkg = make_package("1.8.9", inside="1.8.8")  # app.json claims 1.8.9, code is 1.8.8
        with self.assertRaisesRegex(updater.UpdateError, "mismatched"):
            self.install(pkg)
        self.assertFalse((self.app / "1.8.9").exists())
        self.assertEqual(updater.read_pointer(self.app), (None, None))

    def test_mislabeled_metadata_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, "mismatched"):
            self.install(make_package("1.8.9", meta_version="1.8.8"))

    def test_package_needing_newer_launcher_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, "newer ModDiver Laboratory launcher"):
            self.install(make_package("1.8.9", min_launcher=3), api=2)
        self.assertFalse((self.app / "1.8.9").exists())

    def test_unsafe_paths_are_refused(self):
        for bad in ("../evil.txt", "/abs.txt", "C:/win.txt", "a/../../b.txt", "..\\evil.txt"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(updater.UpdateError, "unsafe path"):
                    self.install(make_package("1.8.9", extra={bad: "x"}))
        self.assertFalse((self.data / "evil.txt").exists())
        self.assertFalse((self.app / "1.8.9").exists())

    def test_sha256_mismatch_is_refused(self):
        pkg = make_package("1.8.9")
        rel = release_for(pkg)
        rel["sha256"] = "0" * 64
        with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
            self.install(pkg, rel)

    def test_size_mismatch_is_refused(self):
        pkg = make_package("1.8.9")
        with self.assertRaisesRegex(updater.UpdateError, "incomplete|size"):
            self.install(pkg, release_for(pkg, size=len(pkg) + 5))

    def test_reinstalling_same_version_is_idempotent(self):
        pkg = make_package("1.8.9")
        self.install(pkg)
        self.install(pkg)
        self.assertEqual(updater.read_pointer(self.app), ("1.8.9", None))

    def test_interrupted_previous_attempt_is_moved_aside(self):
        (self.app / "1.8.9").mkdir(parents=True)
        (self.app / "1.8.9" / "half.txt").write_text("partial")  # no .app-ok marker
        self.install(make_package("1.8.9"))
        self.assertTrue((self.app / "1.8.9" / updater.OK_MARKER).is_file())
        self.assertFalse((self.app / "1.8.9" / "half.txt").exists())

    def test_missing_data_dir_is_a_clear_error(self):
        with self.assertRaisesRegex(updater.UpdateError, "data folder"):
            updater.install_update(release_for(make_package("1.8.9")), "", 2)


class FindUpdateTests(unittest.TestCase):
    @staticmethod
    def api(tag, assets):
        body = json.dumps({"tag_name": tag, "html_url": "https://github.com/x/y/releases/tag/" + tag,
                           "assets": assets}).encode()
        return mock.patch.object(updater.urllib.request, "urlopen", lambda *a, **k: FakeResponse(body))

    @staticmethod
    def asset(version, **over):
        a = {"name": updater.APP_ASSET_TEMPLATE.format(version=version), "state": "uploaded", "size": 5000,
             "browser_download_url": updater.DOWNLOAD_PREFIX + f"v{version}/x.zip", "digest": "sha256:" + "ab" * 32}
        a.update(over)
        return a

    def test_up_to_date_returns_none(self):
        with self.api("v1.8.8", [self.asset("1.8.8")]):
            self.assertIsNone(updater.find_update("1.8.8"))

    def test_newer_release_returns_app_asset(self):
        with self.api("v1.8.9", [self.asset("1.8.9")]):
            rel = updater.find_update("1.8.8")
        self.assertEqual(rel["version"], "1.8.9")
        self.assertEqual(rel["sha256"], "ab" * 32)

    def test_one_gib_package_allowed_and_larger_package_refused(self):
        with self.api('v2.1.1', [self.asset('2.1.1', size=1024**3)]):
            self.assertEqual(updater.find_update('2.1.0')['asset_size'], 1024**3)
        with self.api('v2.1.1', [self.asset('2.1.1', size=1024**3 + 1)]):
            with self.assertRaisesRegex(updater.UpdateError, 'size'):
                updater.find_update('2.1.0')

    def test_download_stream_is_closed_after_verification_failure(self):
        import tempfile
        package = b'payload'
        stream = tempfile.TemporaryFile()
        release = release_for(package)
        release['sha256'] = '0' * 64
        with mock.patch.object(updater.tempfile, 'TemporaryFile', return_value=stream), \
                mock.patch.object(updater.urllib.request, 'urlopen', return_value=FakeResponse(package)):
            with self.assertRaisesRegex(updater.UpdateError, 'SHA-256'):
                updater._download(release)
        self.assertTrue(stream.closed)

    def test_missing_digest_is_allowed(self):
        with self.api("v1.8.9", [self.asset("1.8.9", digest=None)]):
            self.assertEqual(updater.find_update("1.8.8")["sha256"], "")

    def test_release_without_app_package_points_to_manual_download(self):
        with self.api("v1.8.9", [{"name": "ModDiver-Laboratory-Windows.zip", "state": "uploaded"}]):
            with self.assertRaisesRegex(updater.UpdateError, "manually"):
                updater.find_update("1.8.8")

    def test_foreign_download_url_is_refused(self):
        with self.api("v1.8.9", [self.asset("1.8.9", browser_download_url="https://evil.example/x.zip")]):
            with self.assertRaisesRegex(updater.UpdateError, "did not match"):
                updater.find_update("1.8.8")

    def test_version_comparison(self):
        self.assertTrue(updater._is_newer("v1.8.10", "1.8.9"))
        self.assertFalse(updater._is_newer("1.8.8", "1.8.8.0"))
        self.assertEqual(updater.canonical_version("v1.8.9"), "1.8.9")


if __name__ == "__main__":
    unittest.main()
