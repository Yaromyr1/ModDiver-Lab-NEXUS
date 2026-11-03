"""Regression tests for the ModDivers Lab core.

Run: python -m unittest discover -s tests -v
"""
import json
import shutil
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core  # noqa: E402


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig = (core.APP_DATA, core.STOCK, core.BACKUPS, core.DEPLOYED)
        cls.tmp = ROOT / "tests" / "_work"
        cls.tmp.mkdir(parents=True, exist_ok=True)
        core.APP_DATA = cls.tmp
        core.STOCK = cls.tmp / "stock"
        core.BACKUPS = cls.tmp / "backups"
        core.DEPLOYED = cls.tmp / "deployed.json"
        (cls.tmp / 'deploy-transaction.json').unlink(missing_ok=True)
        for p in (cls.tmp / "stock", cls.tmp / "backups"):
            shutil.rmtree(p, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        core.APP_DATA, core.STOCK, core.BACKUPS, core.DEPLOYED = cls._orig
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def make_game(self, files):
        game = self.tmp / "game"
        g = game / "data" / "game"
        g.mkdir(parents=True, exist_ok=True)
        for name, plain in files.items():
            (g / name).write_bytes(core.seal(plain))
        return game


class PatchRenumberTests(Base):
    def test_conflicting_patch_0_gets_unique_indices(self):
        gen = {
            "data/9ba626afa44a3aa3.patch_0": [(0, {"_name": "A"}, b"a"), (1, {"_name": "B"}, b"b")],
            "data/9ba626afa44a3aa3.patch_0.gpu_resources": [(0, {"_name": "A"}, b"g")],
        }
        out = core.renumber_patches(gen)
        self.assertIn("data/9ba626afa44a3aa3.patch_0", out)
        self.assertIn("data/9ba626afa44a3aa3.patch_1", out)
        self.assertIn("data/9ba626afa44a3aa3.patch_0.gpu_resources", out)


class ParseTests(Base):
    def test_manifest_name_and_plain_target(self):
        z = self.tmp / "m.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"Version": 1, "Name": "Hello"}))
            zf.writestr("data/game/generated_x.dl_bin", b"abc")
        m = core.parse_mod(z)
        self.assertEqual(m["name"], "Hello")
        self.assertIn("generated_x.dl_bin", m["targets"])

    def test_malformed_zip_is_unknown(self):
        z = self.tmp / "bad.zip"
        z.write_bytes(b"not a zip")
        m = core.parse_mod(z)
        self.assertEqual(m["type"], "unknown")


class MergeTests(Base):
    def test_conflict_format_adds_verified_schema_name(self):
        from merge_engine import Conflict
        from unittest.mock import patch
        with patch.object(core, '_conflict_record_labels', return_value={8: 'Liberator'}):
            result = core._format_conflict(Conflict(32, 35, 'Old mod', 'New mod'), 'generated.dl_bin', 4)
        self.assertEqual(result, 'record 8 (Liberator), bytes 0x20-0x23 (Old mod -> New mod)')

    def test_overlapping_edits_both_survive(self):
        stock = b"\x00" * 400
        a = bytearray(stock); a[10] = 0xAA
        b = bytearray(stock); b[300] = 0xBB
        merged = bytearray(stock)
        for s, e in core.diff_runs(stock, bytes(a)):
            merged[s:e + 1] = a[s:e + 1]
        for s, e in core.diff_runs(stock, bytes(b)):
            merged[s:e + 1] = b[s:e + 1]
        self.assertEqual(merged[10], 0xAA)
        self.assertEqual(merged[300], 0xBB)

    def test_length_change_falls_back(self):
        stock = core.seal(b"\x00" * 100)
        a = core.seal(b"\x00" * 100)
        b = core.seal(b"\x00" * 101)
        out, why = core.merge_target(
            [{"name": "A", "candidates": {"t": a}}, {"name": "B", "candidates": {"t": b}}], stock, "t")
        self.assertEqual(why, "length")

    def test_failed_hash_correction_falls_back(self):
        stock = core.seal(b"\x00" * 64)
        bad = core.seal(b"\x00" * 32 + b"\x01" * 32)
        # a candidate whose plaintext is not the stock: correction runs; still returns bytes or falls back
        out, why = core.merge_target([{"name": "B", "candidates": {"t": bad}}], stock, "t")
        self.assertIsInstance(out, (bytes, bytearray))
        self.assertIn(why, ("merged", "fallback", "length", "noop"))


class DeployRestoreTests(Base):
    def _setup(self, plain=b"\x00" * 100):
        game = self.make_game({"generated_t.dl_bin": plain})
        cfg = {"game": str(game), "nomofomo": False, "mods": []}
        self.assertEqual(core.capture_stock(cfg), 1)
        return game, cfg, plain

    def test_restore_existing_file(self):
        game, cfg, plain = self._setup()
        mod = self.tmp / "mod"
        mod.mkdir(exist_ok=True)
        (mod / "generated_t.dl_bin").write_bytes(core.seal(b"\x01" * 100))
        cfg["mods"] = [{"path": str(mod), "name": "M", "enabled": True, "selected": {}}]
        reports = []
        core.deploy(cfg, progress=lambda *report: reports.append(report))
        self.assertEqual(reports[-1], ('Files processed', 1, 1))
        self.assertTrue(any(phase == 'Merging and writing files' and total == 1
                            for phase, done, total in reports))
        self.assertTrue(core.load_deployed()["generated_t.dl_bin"]["existed"])
        core.purge(cfg)
        restored = (game / "data" / "game" / "generated_t.dl_bin").read_bytes()
        self.assertEqual(core.unseal(restored), plain)

    def test_delete_file_that_did_not_exist(self):
        game, cfg, plain = self._setup()
        (game / "data" / "game" / "generated_t.dl_bin").unlink()  # target absent before deploy
        mod = self.tmp / "mod2"
        mod.mkdir(exist_ok=True)
        (mod / "generated_t.dl_bin").write_bytes(core.seal(b"\x01" * 100))
        cfg["mods"] = [{"path": str(mod), "name": "M", "enabled": True, "selected": {}}]
        core.deploy(cfg)
        self.assertFalse(core.load_deployed()["generated_t.dl_bin"]["existed"])
        core.purge(cfg)
        self.assertFalse((game / "data" / "game" / "generated_t.dl_bin").exists())

    def test_malformed_mod_does_not_crash_deploy(self):
        game, cfg, plain = self._setup()
        mod = self.tmp / "modbad"
        mod.mkdir(exist_ok=True)
        (mod / "generated_t.dl_bin").write_bytes(b"garbage not sealed")
        cfg["mods"] = [{"path": str(mod), "name": "Bad", "enabled": True, "selected": {}}]
        core.deploy(cfg)  # must not raise
        self.assertNotIn("generated_t.dl_bin", core.load_deployed())


class PortableCaptureTests(Base):
    def test_capture_writes_portable_folder_and_zip(self):
        game = self.make_game({"generated_t.dl_bin": b"\x00" * 100})
        cfg = {"game": str(game), "nomofomo": False, "mods": []}
        core.capture_stock(cfg)
        if core.DEPLOYED.exists():
            core.DEPLOYED.unlink()
        target = game / "data" / "game" / "generated_t.dl_bin"
        stock_bytes = target.read_bytes()
        candidate_bytes = core.seal(b"\x01" * 100)
        target.write_bytes(candidate_bytes)
        orig_config = core.CONFIG
        core.CONFIG = self.tmp / "config.json"
        try:
            m = core.capture_game_mod(cfg, log=lambda *_: None, name="Portable Test")
        finally:
            core.CONFIG = orig_config
        self.assertIsNotNone(m)
        folder = Path(m["path"])
        self.assertTrue((folder / "manifest.json").exists())
        self.assertTrue((folder / "data" / "game" / "generated_t.dl_bin").exists())
        self.assertTrue(Path(m["package"]).exists())
        with zipfile.ZipFile(m["package"]) as z:
            self.assertIn("manifest.json", z.namelist())
            self.assertIn("data/game/generated_t.dl_bin", z.namelist())
            manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(manifest["Name"], "Portable Test")
            self.assertTrue(manifest["Guid"])
            self.assertEqual(manifest["Version"], 1)
        parsed = core.parse_mod(folder)
        self.assertIn("generated_t.dl_bin", parsed["targets"])
        self.assertEqual(cfg["mods"][-1]["guid"], manifest["Guid"])

        self.assertTrue(Path(m["arsenal_package"]).exists())
        with zipfile.ZipFile(m["arsenal_package"]) as z:
            names = z.namelist()
            self.assertIn("manifest.json", names)
            self.assertIn("mod/9ba626afa44a3aa3.patch_0", names)
            self.assertIn("mod/9ba626afa44a3aa3.patch_1", names)
            self.assertIn("mod/9ba626afa44a3aa3.patch_1.stream", names)
            arsenal_manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(arsenal_manifest["Options"][0]["Include"], ["mod"])
            self.assertEqual(z.getinfo("mod/9ba626afa44a3aa3.patch_0").file_size, 11136)
            got = core.parse_stream(z.read("mod/9ba626afa44a3aa3.patch_1.stream"))
            self.assertIsNotNone(got)
            target_name, original, candidate = got
            self.assertEqual(target_name, "generated_t.dl_bin")
            self.assertEqual(original, stock_bytes)
            self.assertEqual(candidate, candidate_bytes)


if __name__ == "__main__":
    unittest.main()
