import io
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import core
import gameplay_profiles
from archive_codec import Archive
from asset_mods import Project


def resource_archive(kind=0xcd4238c6a0c69e32, payload=b'metadata', gpu=b'pixels'):
    head = struct.pack('<III', 0xf0000011, 1, 1) + b'\0'*60
    types = struct.pack('<QQQII', 0, kind, 1, 16, 16)
    row = struct.pack('<7Q6I', 123, kind, 184, 0, 0, 0, 0, len(payload), 0, len(gpu), 16, 16, 0)
    return Archive('9ba626afa44a3aa3.patch_0', (head+types+row+payload, b'', gpu))


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_texture_and_sound_copy_roundtrip_importable_mod(self):
        for type_hash in (0xcd4238c6a0c69e32, 0x504b55235d21440e):
            source = resource_archive(type_hash)
            donor = resource_archive(type_hash, b'new metadata', b'new encoded content')
            project = Project(self.root/'source.zip', [source])
            project.copy_resource(0, 0, donor, 0)
            out = project.export_mod(self.root/'output.zip', 'My mod')
            parsed = core.parse_mod(out)
            self.assertTrue(parsed['targets'])
            reopened = Project.open(out).archives[0]
            for section in range(3):
                self.assertEqual(reopened.payload(0, section), donor.payload(0, section))
            self.assertEqual(reopened.resources[0].name_hash, 123)
            project.restore(0, 0)
            self.assertFalse(project.changed)

    def test_bundle_import_checks_type_before_staging(self):
        project = Project('source.zip', [resource_archive()])
        project.export_bundle(0, 0, self.root/'asset.zip')
        other = Project('sound.zip', [resource_archive(0x504b55235d21440e)])
        with self.assertRaises(ValueError):
            other.import_bundle(0, 0, self.root/'asset.zip')
        self.assertFalse(other.changed)
        with zipfile.ZipFile(self.root/'asset.zip') as z:
            entries = {n:z.read(n) for n in z.namelist()}
        entries['gpu.bin'] = b'edited texture pixels'
        with zipfile.ZipFile(self.root/'asset.zip', 'w') as z:
            for n, data in entries.items(): z.writestr(n, data)
        project.import_bundle(0, 0, self.root/'asset.zip')
        self.assertEqual(project.archives[0].payload(0, 2), b'edited texture pixels')

    def test_wrong_donor_type_and_source_overwrite_rejected(self):
        project = Project(self.root/'source.zip', [resource_archive()])
        with self.assertRaises(ValueError):
            project.copy_resource(0, 0, resource_archive(0x504b55235d21440e), 0)
        self.assertFalse(project.changed)
        with self.assertRaises(ValueError): project.export_mod(self.root/'source.zip', 'Name')
        with self.assertRaises(ValueError): project.export_bundle(0, 0, self.root/'source.zip')
        loose = resource_archive()
        loose.path = self.root/loose.path.name
        project = Project(loose.path, [loose])
        with self.assertRaises(ValueError):
            project.export_bundle(0, 0, str(loose.path)+'.gpu_resources')

    def test_zip_opens_install_group_not_uninstaller(self):
        source = resource_archive()
        with zipfile.ZipFile(self.root/'sample.zip', 'w') as z:
            for folder in ('Install', 'UninstallHelper'):
                for suffix, data in zip(('', '.stream', '.gpu_resources'), source.blobs):
                    z.writestr(folder+'/'+source.path.name+suffix, data)
        self.assertEqual(len(Project.open(self.root/'sample.zip').archives), 1)


class GameplayProfileTests(unittest.TestCase):
    def test_bundled_payloads_validate_and_require_supported_stock(self):
        with tempfile.TemporaryDirectory() as folder:
            for key in gameplay_profiles.PROFILES:
                with self.assertRaisesRegex(ValueError, 'clean stock'):
                    gameplay_profiles.build_mod(key, folder)
                with zipfile.ZipFile(core.BUILTIN/'gameplay'/(key+'.zip')) as z:
                    meta = json.loads(z.read('profile.json'))
                    payload = z.read(meta['target'])
                core.validate_sealed_input(payload, key)
                core.unseal(payload)
                self.assertIn(gameplay_profiles.fingerprint(payload), meta['mod_fingerprints'])
                target = Path(folder)/Path(meta['target']).name
                target.write_bytes(b'fake clean stock')
                with patch.object(gameplay_profiles, 'fingerprint', return_value=meta['stock_fingerprints'][0]):
                    mod = gameplay_profiles.build_mod(key, folder)
                    self.assertEqual(mod['candidates'][Path(meta['target']).name], payload)
                target.unlink()

    def test_profiles_default_off_and_selected_profiles_run_before_writes(self):
        with patch.object(gameplay_profiles, 'build_mod', side_effect=ValueError('wrong build')) as build:
            with self.assertRaisesRegex(ValueError, 'wrong build'):
                core.deploy({'mods': [], 'nomofomo': False, 'consistent_vaulting': True})
            build.assert_called_once_with('consistent_vaulting', core.STOCK)
            build.reset_mock()
            self.assertEqual(core.deploy({'mods': [], 'nomofomo': False}, lambda _: None), 0)
            build.assert_not_called()

    def test_profile_deploy_and_purge_restore_owned_game_file(self):
        key = 'stratagem_bounce_removed'
        with zipfile.ZipFile(core.BUILTIN/'gameplay'/(key+'.zip')) as z:
            meta = json.loads(z.read('profile.json'))
            payload = z.read(meta['target'])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stock = root/'stock'; stock.mkdir()
            # A sealed fixture baseline; witness matching is tested separately.
            baseline = core.seal(b'fixture baseline'*8)
            (stock/Path(meta['target']).name).write_bytes(baseline)
            game = root/'game'; target = game/meta['target']
            target.parent.mkdir(parents=True); target.write_bytes(baseline)
            cfg = {'game': str(game), 'mods': [], 'nomofomo': False, key: True}
            with patch.multiple(core, STOCK=stock, BACKUPS=root/'backups', DEPLOYED=root/'deployed.json'), \
                 patch.object(gameplay_profiles, 'fingerprint', return_value=meta['stock_fingerprints'][0]):
                self.assertEqual(core.deploy(cfg, lambda _: None, dry_run=True), 1)
                self.assertEqual(target.read_bytes(), baseline)
                self.assertEqual(core.deploy(cfg, lambda _: None), 1)
                self.assertEqual(target.read_bytes(), payload)
                self.assertEqual(core.purge(cfg, lambda _: None), 1)
                self.assertEqual(target.read_bytes(), baseline)
