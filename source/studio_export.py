"""One manager-ready pack from completed audio and visual resource patches."""
import io
import json
from pathlib import Path
import re
import struct
import uuid
import zipfile

from archive_codec import Archive, MAGIC, SUFFIXES
from merge_engine import atomic_write

PATCH = re.compile(r'^([0-9a-fA-F]{16})\.patch_(\d+)(\.stream|\.gpu_resources)?$')


def resource_rows(archive, indices=None):
    type_rows = {}
    for i in range(archive.type_count):
        row = archive.blobs[0][72+32*i:104+32*i]
        type_rows[struct.unpack_from('<Q', row, 8)[0]] = row
    for index in (range(len(archive.resources)) if indices is None else indices):
        resource = archive.resources[index]
        start = archive.table_offset+80*index
        yield (resource, tuple(archive.payload(index, s) for s in range(3)),
               archive.blobs[0][start:start+80], type_rows[resource.type_hash])


def resource_patch(resources, header=None):
    """Build a compact native container while retaining resource/type metadata."""
    resources = sorted(resources, key=lambda row: (row[0].type_hash, row[0].name_hash))
    types = sorted({row[0].type_hash for row in resources})
    header = bytearray(header[:72] if header else struct.pack('<III', MAGIC, 0, 0)+bytes(60))
    struct.pack_into('<III', header, 0, MAGIC, len(types), len(resources))
    for kind in types:
        row = bytearray(next(row[3] for row in resources if row[0].type_hash == kind))
        struct.pack_into('<Q', row, 16, sum(row[0].type_hash == kind for row in resources))
        header += row
    table = len(header)
    header += bytes(80 * len(resources) + 8)
    blobs = [header, bytearray(), bytearray()]
    for index, (resource, payloads, record, _) in enumerate(resources):
        offsets = []
        for section, payload in enumerate(payloads):
            blobs[section] += bytes(-len(blobs[section]) % (16 if section == 0 else 64))
            offsets.append(len(blobs[section]) if payload else 0)
            blobs[section] += payload
        row = bytearray(record)
        struct.pack_into('<QQQ', row, 16, *offsets)
        struct.pack_into('<III', row, 56, *(len(p) for p in payloads))
        struct.pack_into('<I', row, 76, index)
        blobs[0][table+80*index:table+80*(index+1)] = row
    if len(blobs[0]) < 256*len(resources):
        blobs[0] += bytes(256*len(resources)-len(blobs[0]))
    output = tuple(bytes(blob) for blob in blobs)
    check = Archive('0000000000000000.patch_0', output)
    for index, (_, payloads, _, _) in enumerate(resources):
        for section, payload in enumerate(payloads):
            if check.payload(index, section) != payload:
                raise ValueError('Finished mod resource verification failed.')
    return output


def visual_patches(project):
    """Export only explicitly changed resources, avoiding untouched audio banks."""
    groups = []
    for archive in project.archives:
        indices = sorted({index for index, _ in archive.replacements})
        if not indices: continue
        base = archive.path.name.split('.')[0].lower()
        if not re.fullmatch('[0-9a-f]{16}', base):
            raise ValueError('A visual source is missing its original archive ID.')
        groups.append((base, resource_patch(resource_rows(archive, indices), archive.blobs[0])))
    return groups


def zip_patches(filename):
    """Read a completed patch pack using its default option selection."""
    import core
    parsed = core.parse_mod(filename)
    if parsed.get('hellforge') or parsed.get('candidates') or parsed.get('runtime'):
        raise ValueError('Choose a finished audio/visual patch ZIP. Native gameplay/code packages belong in Mod Library.')
    defaults = {opt['name']: opt.get('default', True) for opt in parsed.get('options', [])}
    files = {}
    for entry in parsed.get('files', []):
        if entry.get('option') and not defaults.get(entry['option'], True): continue
        name = Path(entry['target']).name
        if not PATCH.fullmatch(name):
            raise ValueError('Finished audio/visual exports can contain native patch resources only.')
        if name in files and files[name] != entry['data']:
            raise ValueError('The input has conflicting default options. Export one variant first.')
        files[name] = entry['data']
    mains = sorted((n for n in files if PATCH.fullmatch(n).group(3) is None),
                   key=lambda n: (PATCH.fullmatch(n).group(1).lower(), int(PATCH.fullmatch(n).group(2))))
    if not mains:
        raise ValueError('This ZIP has no installable audio/visual patch groups.')
    for name in files:
        match = PATCH.fullmatch(name)
        if match.group(3) and name[:-len(match.group(3))] not in mains:
            raise ValueError('A patch sidecar is missing its main archive: ' + name)
    return [(PATCH.fullmatch(n).group(1).lower(), tuple(files.get(n+s, b'') for s in SUFFIXES)) for n in mains]


def export(filename, name, sources, *, description='', target='Selected game', guid=None, icon=None):
    """Merge resource groups per source; refuse ambiguous cross-source collisions.

    sources is [(label, [(archive ID, three blobs), ...]), ...]. Later patches
    within a source follow game priority. Different sources must agree on any
    shared resource: choosing a silent winner could discard audio or visuals.
    """
    import core
    if not name.strip(): raise ValueError('Enter a name for the finished mod.')
    combined, owners, headers = {}, {}, {}
    for label, groups in sources:
        current = {}
        for base, blobs in groups:
            if not re.fullmatch('[0-9a-f]{16}', base):
                raise ValueError('A source is missing a valid 16-digit archive ID.')
            archive = Archive(base+'.patch_0', blobs)
            headers.setdefault(base, blobs[0][:72])
            for row in resource_rows(archive):
                resource = row[0]
                key = (base, resource.name_hash, resource.type_hash)
                current[key] = row
        for key, resource in current.items():
            if key in combined and combined[key][1] != resource[1]:
                raise ValueError(f'{owners[key]} and {label} change the same resource ({key[1]:016x}). '
                                 'Resolve that overlap before combining; your previous export is preserved.')
            combined[key], owners[key] = resource, label
    if not combined: raise ValueError('Include at least one edited project or finished patch ZIP.')
    manifest = {'Version': 1, 'Guid': str(uuid.UUID(guid)) if guid else str(uuid.uuid4()),
                'Name': name.strip(), 'Description': description.strip(),
                'ModDiverStudio': 1,
                'Options': [{'Name': name.strip(), 'Include': ['data']} ]}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as package:
        for base in sorted({key[0] for key in combined}):
            rows = [combined[key] for key in sorted(combined) if key[0] == base]
            for suffix, blob in zip(SUFFIXES, resource_patch(rows, headers[base])):
                if blob: package.writestr('data/'+base+'.patch_0'+suffix, blob)
        if icon and Path(icon).is_file():
            package.writestr('icon.png', Path(icon).read_bytes()); manifest['IconPath'] = 'icon.png'
        package.writestr('manifest.json', json.dumps(manifest, indent=2))
        package.writestr('README.txt', f'{name.strip()}\n\nImport this ZIP into your HD2 mod manager and enable it. '
                          'Do not import it as an editable project.\n'
                          f'Built for: {target}. Use the same game copy/version it was created against.\n'
                          'HellForge: add the pack to Mods and press PLAY in HellForge.\n')
        package.writestr('moddiver-studio.json', json.dumps({'format':1, 'target':target,
                          'resources':len(combined), 'sources':[label for label, _ in sources]}, indent=2))
    # Verify ZIP integrity before replacing the previous completed export.
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as check:
        if check.testzip(): raise ValueError('Finished mod ZIP verification failed.')
    atomic_write(filename, buffer.getvalue())
    return Path(filename)
