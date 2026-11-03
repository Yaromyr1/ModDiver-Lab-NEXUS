"""Safety and priority regression tests for the consolidated build.

Run: python -m unittest discover -s tests -v
"""
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
        cls.tmp = ROOT / "tests" / "_work_safety"
        cls.tmp.mkdir(parents=True, exist_ok=True)
        core.APP_DATA = cls.tmp
        core.STOCK = cls.tmp / "stock"
        core.BACKUPS = cls.tmp / "backups"
        core.DEPLOYED = cls.tmp / "deployed.json"
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


class PathTraversalTests(Base):
    def test_target_inside_data_is_ok(self):
        game = self.make_game({})
        cfg = {"game": str(game)}
        p = core.target_path(cfg, "data/game/generated_x.dl_bin")
        self.assertTrue(str(p).endswith("generated_x.dl_bin"))

    def test_target_escape_is_rejected(self):
        game = self.make_game({})
        cfg = {"game": str(game)}
        for bad in ("data/../../escape.dl_bin", "data/..\\..\\escape.dl_bin",
                    "data/game/../../escape.dl_bin", "/abs/escape.dl_bin"):
            with self.assertRaises(RuntimeError):
                core.target_path(cfg, bad)

    def test_parse_skips_traversal_targets(self):
        z = self.tmp / "evil.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("data/../../evil.txt", b"x")
            zf.writestr("data/game/generated_ok.dl_bin", b"x")
        m = core.parse_mod(z)
        self.assertNotIn("data/../../evil.txt", m["targets"])
        self.assertIn("generated_ok.dl_bin", m["targets"])


class CaptureTests(Base):
    def test_recapture_removes_stale_stock(self):
        game = self.make_game({"generated_a.dl_bin": b"A" * 100,
                               "generated_b.dl_bin": b"B" * 100})
        cfg = {"game": str(game), "nomofomo": False, "mods": []}
        self.assertEqual(core.capture_stock(cfg), 2)
        (game / "data" / "game" / "generated_b.dl_bin").unlink()
        self.assertEqual(core.capture_stock(cfg), 1)
        names = sorted(p.name for p in core.STOCK.glob("*.dl_bin"))
        self.assertEqual(names, ["generated_a.dl_bin"])


class PriorityTests(Base):
    def _deploy_two(self, value_top, value_bottom):
        game = self.make_game({"generated_t.dl_bin": b"\x00" * 100})
        cfg = {"game": str(game), "nomofomo": False, "mods": []}
        core.capture_stock(cfg)
        mods = []
        for i, value in enumerate((value_top, value_bottom)):
            d = self.tmp / f"mod{i}"
            d.mkdir(exist_ok=True)
            (d / "generated_t.dl_bin").write_bytes(core.seal(bytes([value]) * 100))
            mods.append({"path": str(d), "name": f"M{i}", "enabled": True, "selected": {}})
        cfg["mods"] = mods
        core.deploy(cfg)
        return core.unseal((game / "data" / "game" / "generated_t.dl_bin").read_bytes())

    def test_top_mod_wins(self):
        result = self._deploy_two(0x11, 0x22)
        # list order: M0 (top) then M1; the TOP mod must win
        self.assertEqual(result[0], 0x11)

    def test_same_value_is_not_a_conflict(self):
        result = self._deploy_two(0x33, 0x33)
        self.assertEqual(result[0], 0x33)


class PurgeBackupTests(Base):
    def test_purge_clears_backups(self):
        game = self.make_game({"generated_t.dl_bin": b"\x00" * 100})
        cfg = {"game": str(game), "nomofomo": False, "mods": []}
        core.capture_stock(cfg)
        d = self.tmp / "modp"
        d.mkdir(exist_ok=True)
        (d / "generated_t.dl_bin").write_bytes(core.seal(b"\x01" * 100))
        cfg["mods"] = [{"path": str(d), "name": "P", "enabled": True, "selected": {}}]
        core.deploy(cfg)
        core.purge(cfg)
        self.assertEqual(core.load_deployed(), {})
        leftovers = list(core.BACKUPS.glob("*")) if core.BACKUPS.exists() else []
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
