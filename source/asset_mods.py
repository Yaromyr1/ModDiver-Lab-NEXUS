"""Native texture/audio resource replacement and portable archive mod packaging."""
import io
import json
import re
import uuid
import zipfile
from pathlib import Path

from archive_codec import Archive, SECTIONS, SUFFIXES
from merge_engine import atomic_write

TYPES = {0xcd4238c6a0c69e32: 'Texture', 0x504b55235d21440e: 'Sound stream',
         0x535a7bd3e650d799: 'Sound bank', 0xaf32095c82f2b070: 'Sound dependencies',
         0xeac0b497876adedf: 'Material', 0xe0a48d0be9a7453f: 'Model / unit'}
MAIN = re.compile(r'^[0-9a-fA-F]{16}(?:\.patch_\d+)?$')
LIMIT = 1024 ** 3


def kind(resource):
    return TYPES.get(resource.type_hash, f'Other ({resource.type_hash:016x})')


class Project:
    def __init__(self, source, archives):
        if not archives:
            raise ValueError('No supported archive groups found. Choose a main archive or a mod ZIP.')
        names = [a.path.name for a in archives]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate archive filenames. Open one variant at a time.')
        self.source, self.archives = Path(source), archives
        self.revision = 0

    @classmethod
    def open(cls, source):
        path = Path(source)
        if path.suffix.lower() != '.zip':
            return cls(path, [Archive.open(path)])
        archives = []
        with zipfile.ZipFile(path) as package:
            infos = package.infolist()
            names = [info.filename for info in infos]
            if len(set(names)) != len(names):
                raise ValueError('ZIP has duplicate entries.')
            if sum(i.file_size for i in infos) > LIMIT:
                raise ValueError('Mod ZIP exceeds the 1 GiB uncompressed editor limit.')
            for name in names:
                parts = name.replace('\\', '/').split('/')
                if any(p.casefold().startswith('uninstall') for p in parts):
                    continue
                if MAIN.fullmatch(parts[-1]):
                    blobs = tuple(package.read(name+s) if name+s in names else b'' for s in SUFFIXES)
                    archives.append(Archive(parts[-1], blobs))
        return cls(path, archives)

    @property
    def changed(self):
        return any(a.replacements for a in self.archives)

    def check_output(self, filename):
        sources = {self.source.resolve()}
        if self.source.suffix.lower() != '.zip':
            sources.update(Path(str(a.path)+suffix).resolve() for a in self.archives for suffix in SUFFIXES)
        if Path(filename).resolve() in sources:
            raise ValueError('Choose a new output file to preserve the source mod and its sidecars.')

    def copy_resource(self, archive_index, resource_index, donor, donor_index):
        target = self.archives[archive_index]
        if target.resources[resource_index].type_hash != donor.resources[donor_index].type_hash:
            raise ValueError('Replacement resource type must match the selected resource.')
        # Copy metadata and all sidecar payloads as a unit, retaining the target ID.
        for section in range(3):
            target.replace(resource_index, section, donor.payload(donor_index, section))
        self.revision += 1

    def export_bundle(self, archive_index, resource_index, filename):
        self.check_output(filename)
        archive = self.archives[archive_index]
        resource = archive.resources[resource_index]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as package:
            package.writestr('resource.json', json.dumps({'format': 'moddiver-native-asset-1',
                'type_hash': f'{resource.type_hash:016x}', 'name_hash': f'{resource.name_hash:016x}'}, indent=2))
            for section, name in enumerate(SECTIONS):
                package.writestr(name+'.bin', archive.payload(resource_index, section))
        atomic_write(filename, buffer.getvalue())

    def import_bundle(self, archive_index, resource_index, filename):
        archive = self.archives[archive_index]
        with zipfile.ZipFile(filename) as package:
            if sum(i.file_size for i in package.infolist()) > LIMIT:
                raise ValueError('Resource bundle exceeds the 1 GiB editor limit.')
            meta = json.loads(package.read('resource.json'))
            if meta.get('format') != 'moddiver-native-asset-1' or int(meta['type_hash'], 16) != archive.resources[resource_index].type_hash:
                raise ValueError('Resource bundle format or type does not match the target.')
            payloads = [package.read(s+'.bin') for s in SECTIONS]
        for section, data in enumerate(payloads):
            archive.replace(resource_index, section, data)
        self.revision += 1

    def restore(self, archive_index, resource_index):
        archive = self.archives[archive_index]
        for section in range(3):
            archive.replacements.pop((resource_index, section), None)
        self.revision += 1

    def export_mod(self, filename, name):
        target = Path(filename)
        self.check_output(target)
        if not str(name).strip():
            raise ValueError('Enter a mod name.')
        if not self.changed:
            raise ValueError('Replace at least one resource before exporting a mod.')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as package:
            package.writestr('manifest.json', json.dumps({'Version': 1, 'Guid': str(uuid.uuid4()),
                'Name': name.strip(), 'Description': 'Native visual/audio replacements created with ModDiver Laboratory.'}, indent=2))
            for archive in self.archives:
                if not MAIN.fullmatch(archive.path.name):
                    raise ValueError('Source needs its original 16-digit archive ID / .patch_N filename.')
                basename = archive.path.name if '.patch_' in archive.path.name else archive.path.name+'.patch_0'
                blobs = archive.rebuild()
                check = Archive(basename, blobs)
                for (index, section), expected in archive.replacements.items():
                    if check.payload(index, section) != expected:
                        raise ValueError('Exported resource verification failed.')
                for suffix, data in zip(SUFFIXES, blobs):
                    package.writestr(basename+suffix, data)
            package.writestr('README.txt', 'Import this ZIP in ModDiver Laboratory, then use Merge and Install All.\n'
                'Includes native resources and their matching sidecars. Test compatibility with your game build.\n')
        atomic_write(target, buffer.getvalue())
        return target
