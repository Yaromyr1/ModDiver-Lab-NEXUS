"""Native reader and conservative repacker for uncompressed HD2 Stingray containers.

The 72-byte header, 32-byte type rows and 80-byte resource rows are retained.
Edited payloads are appended, so unknown metadata and unedited data survive intact.
Resource-specific binary schemas are intentionally not inferred.
"""
from dataclasses import dataclass
from pathlib import Path
import struct

from merge_engine import atomic_write

MAGIC = 0xF0000011
MAX_BYTES = 2 * 1024 ** 3
SECTIONS = ("main", "stream", "gpu")
SUFFIXES = ("", ".stream", ".gpu_resources")
LUA_TYPE = 0xA14E8DFA2CD117E2


@dataclass(frozen=True)
class Resource:
    index: int
    name_hash: int
    type_hash: int
    offsets: tuple
    sizes: tuple


class Archive:
    def __init__(self, path, blobs):
        self.path = Path(path)
        self.blobs = tuple(blobs)
        self.replacements = {}
        main = self.blobs[0]
        if len(main) < 72:
            raise ValueError("Archive header is truncated.")
        magic, self.type_count, count = struct.unpack_from("<III", main)
        if magic != MAGIC:
            raise ValueError("Unsupported archive signature. Select an uncompressed Stingray archive or .patch_N main file.")
        self.table_offset = 72 + 32 * self.type_count
        table_end = self.table_offset + 80 * count
        if self.type_count > 100000 or count > 1000000 or table_end > len(main):
            raise ValueError("Resource table is truncated or has invalid counts.")
        self.resources = []
        for index in range(count):
            row = self.table_offset + 80 * index
            fields = struct.unpack_from("<7Q6I", main, row)
            resource = Resource(index, fields[0], fields[1], fields[2:5], fields[7:10])
            for section, (offset, size) in enumerate(zip(resource.offsets, resource.sizes)):
                if size and (offset + size > len(self.blobs[section]) or
                             (section == 0 and offset < table_end)):
                    raise ValueError(f"Resource {index}: {SECTIONS[section]} payload lies outside its data file. Check the matching sidecars.")
            self.resources.append(resource)

    @classmethod
    def open(cls, filename):
        path = Path(filename)
        for suffix in SUFFIXES[1:]:
            if str(path).endswith(suffix):
                path = Path(str(path)[:-len(suffix)])
                break
        blobs = []
        for suffix in SUFFIXES:
            component = Path(str(path) + suffix)
            if suffix and not component.exists():
                blobs.append(b"")
                continue
            if component.stat().st_size > MAX_BYTES:
                raise ValueError("Archive component exceeds the 2 GiB editor limit.")
            blobs.append(component.read_bytes())
        return cls(path, blobs)

    def payload(self, index, section):
        if (index, section) in self.replacements:
            return self.replacements[index, section]
        resource = self.resources[index]
        start, size = resource.offsets[section], resource.sizes[section]
        return self.blobs[section][start:start + size]

    def replace(self, index, section, data):
        if not isinstance(data, bytes) or len(data) > MAX_BYTES:
            raise ValueError("Replacement must be binary data of at most 2 GiB.")
        resource = self.resources[index]
        original = self.blobs[section][resource.offsets[section]:resource.offsets[section] + resource.sizes[section]]
        if data == original:
            self.replacements.pop((index, section), None)
        else:
            self.replacements[index, section] = data

    def rebuild(self):
        if not self.replacements:
            return self.blobs
        blobs = [bytearray(blob) for blob in self.blobs]
        for (index, section), payload in sorted(self.replacements.items()):
            blob = blobs[section]
            if payload:
                blob.extend(b"\0" * (-len(blob) % 16))
                offset = len(blob)
                blob.extend(payload)
            else:
                offset = 0
            if len(blob) > MAX_BYTES:
                raise ValueError("Repacked component exceeds the 2 GiB editor limit.")
            row = self.table_offset + 80 * index
            struct.pack_into("<Q", blobs[0], row + (16, 24, 32)[section], offset)
            struct.pack_into("<I", blobs[0], row + (56, 60, 64)[section], len(payload))
        for section in {section for _, section in self.replacements}:
            blobs[section].extend(b"\0" * (-len(blobs[section]) % 16))
        result = tuple(bytes(blob) for blob in blobs)
        check = Archive(self.path, result)
        for key, expected in self.replacements.items():
            if check.payload(*key) != expected:
                raise ValueError("Repacked payload verification failed.")
        return result

    def export(self, filename):
        target = Path(filename)
        if str(target).endswith(SUFFIXES[1:]):
            raise ValueError("Choose the main archive filename, without a sidecar extension.")
        sources = {Path(str(self.path) + suffix).resolve() for suffix in SUFFIXES}
        destinations = [Path(str(target) + suffix) for suffix in SUFFIXES]
        if any(path.resolve() in sources for path in destinations):
            raise ValueError("Export to a new file or folder to keep the original archive intact.")
        blobs = self.rebuild()
        # Write the main table last: it must not reference new sidecar offsets
        # before those sidecars have been fully written.
        for section in (1, 2, 0):
            atomic_write(destinations[section], blobs[section])
        return destinations


def lua_source(payload):
    if len(payload) < 8:
        return None
    length, version = struct.unpack_from("<II", payload)
    if version != 2 or length != len(payload) - 8:
        return None
    try:
        return payload[8:].decode("utf-8")
    except UnicodeDecodeError:
        return None
