"""Inspect supplied repair examples as binary data. Never execute their loaders."""
import hashlib
import struct
import zipfile
from pathlib import Path
import re

from archive_codec import Archive, LUA_TYPE, MAX_BYTES
from dlbin_codec import DLBin, content_hash


def inspect(path):
    rows = []
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            name = entry.filename.replace('\\', '/')
            if not name.lower().startswith('install/') or not re.fullmatch(
                    r'[0-9a-fA-F]{16}\.patch_\d+', name.split('/')[-1]):
                continue
            if entry.file_size > MAX_BYTES:
                raise ValueError('Reference archive exceeds the decoder limit.')
            # Only self-contained, zero-sidecar data wrappers are supported here.
            parsed = Archive(name, (archive.read(entry), b'', b''))
            for resource in parsed.resources:
                raw = parsed.payload(resource.index, 0)
                if resource.type_hash != LUA_TYPE or len(raw) < 18:
                    continue
                length, version = struct.unpack_from('<II', raw)
                if version != 2 or length != len(raw)-8 or raw[8:14] != b'HD2FM1':
                    continue
                header_size = struct.unpack_from('<I', raw, 14)[0]
                if header_size > 1024**2 or header_size > len(raw)-18:
                    raise ValueError('Invalid reference data-wrapper header length.')
                metadata = {}
                for line in raw[18:18+header_size].decode('utf-8').splitlines():
                    key, separator, value = line.partition('=')
                    if not separator:
                        raise ValueError('Invalid reference metadata.')
                    metadata.setdefault(key, []).append(value)
                target = metadata.get('target', [''])[0]
                if not re.fullmatch(r'data/game/generated_[a-zA-Z0-9_]+\.dl_bin', target):
                    raise ValueError('Reference wrapper target is not a supported game-data file.')
                payload = raw[18+header_size:]
                if metadata.get('size') != [str(len(payload))]:
                    raise ValueError('Reference wrapper payload size mismatch.')
                decoded = DLBin(Path(target).name, payload)
                rows.append({'package_entry': name, 'target': target, 'size': len(payload),
                             'sha256': hashlib.sha256(payload).hexdigest(),
                             'decoded_sha256': hashlib.sha256(decoded.plain).hexdigest(),
                             'content_hash': f'{content_hash(decoded.plain):016x}',
                             'blocks': len(decoded.resources), 'metadata': metadata})
    if not rows:
        raise ValueError('No supported embedded HD2FM1 data payloads were found. No package code was executed.')
    return rows


def compare(reference, original):
    rows = inspect(reference)
    with zipfile.ZipFile(original) as archive:
        for row in rows:
            matching = [entry for entry in archive.infolist()
                        if entry.filename.replace('\\', '/').lower().endswith(row['target'].lower())]
            if len(matching) != 1:
                row['comparison'] = 'No unique original data file found.'
                continue
            if matching[0].file_size > MAX_BYTES:
                raise ValueError('Original payload exceeds the decoder limit.')
            payload = archive.read(matching[0])
            decoded = DLBin(Path(row['target']).name, payload)
            if hashlib.sha256(payload).hexdigest() == row['sha256']:
                row['comparison'] = 'Identical sealed gameplay payload; the supplied fix changes packaging/metadata.'
            elif hashlib.sha256(decoded.plain).hexdigest() == row['decoded_sha256']:
                row['comparison'] = 'Identical decoded data; sealed encoding differs.'
            else:
                row['comparison'] = 'Decoded data changed; a gameplay/layout migration may be required.'
    return rows
