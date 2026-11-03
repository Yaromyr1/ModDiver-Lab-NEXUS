"""Sealed LDLD data-file editing with verified content-hash preservation."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import math
from portable_hash import content_hash

import core
from archive_codec import Resource, MAX_BYTES
from merge_engine import atomic_write

NEEDLE = b"LDLD\x01\0\0\0"
MASK = (1 << 64) - 1
MUL = 0xC6A4A7935BD1E995


def blocks(data):
    result = []
    pos = data.find(NEEDLE, 0, min(len(data), 64))
    if pos < 0:
        raise ValueError("Decoded file has no supported LDLD blocks.")
    while pos >= 0:
        if pos + 24 > len(data):
            raise ValueError("Truncated LDLD header.")
        kind, size = struct.unpack_from("<II", data, pos + 8)
        end = pos + 24 + size
        if end > len(data) or data[pos + 16] != 1:
            raise ValueError("Invalid LDLD size or header flag.")
        result.append((pos, kind, size))
        pos = data.find(NEEDLE, end, min(len(data), end + 64))
    return result


class DLBin:
    kind = "dlbin"

    def __init__(self, path, sealed):
        self.path = Path(path)
        self.sealed = sealed
        self.plain = core.unseal(sealed)
        self.headers = blocks(self.plain)
        self.resources = [Resource(i, pos, kind, (pos + 24, 0, 0), (size, 0, 0))
                          for i, (pos, kind, size) in enumerate(self.headers)]
        self.type_count = len({kind for _, kind, _ in self.headers})
        self.replacements = {}
        self.float_edits = {}

    @classmethod
    def open(cls, path):
        path = Path(path)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Data file exceeds the 2 GiB editor limit.")
        return cls(path, path.read_bytes())

    def payload(self, index, section):
        if section != 0:
            return b""
        resource = self.resources[index]
        return self.replacements.get((index, section), self.plain[resource.offsets[0]:resource.offsets[0] + resource.sizes[0]])

    def replace(self, index, section, data, float_offsets=()):
        resource = self.resources[index]
        if section != 0 or len(data) != resource.sizes[0]:
            raise ValueError("LDLD block edits must keep the original byte length. Adding/removing records is not supported.")
        original = self.plain[resource.offsets[0]:resource.offsets[0] + resource.sizes[0]]
        if data == original:
            self.replacements.pop((index, section), None)
            self.float_edits.pop(index, None)
        else:
            previous = self.payload(index, section)
            explicit = set(float_offsets)
            if any(offset % 4 or offset < 0 or offset + 4 > len(data) for offset in explicit):
                raise ValueError("Invalid explicit float edit offset.")
            kept = {offset for offset in self.float_edits.get(index, set())
                    if previous[offset:offset + 4] == data[offset:offset + 4]}
            self.float_edits[index] = kept | explicit
            self.replacements[index, section] = data

    def prepare(self):
        if not self.replacements:
            return self.sealed, []
        candidate = bytearray(self.plain)
        for (index, _), payload in self.replacements.items():
            start = self.resources[index].offsets[0]
            candidate[start:start + len(payload)] = payload
        from portable_hash import correct_reserved
        native = correct_reserved(self.plain, candidate, self.headers)
        if native is not None:
            if content_hash(native) != content_hash(self.plain) or blocks(native) != self.headers:
                raise ValueError('Native hash correction verification failed.')
            for pos, _, size in self.headers:
                if native[pos+24:pos+24+size] != candidate[pos+24:pos+24+size]:
                    raise ValueError('Native correction changed payload data.')
            sealed = core.seal(native)
            if core.unseal(sealed) != native:
                raise ValueError('Native reseal verification failed.')
            return sealed, []
        # Prefer header-only salts whenever another block provides reserved bytes.
        # Single-block files may need a small change to an already edited float;
        # the UI presents that change for approval before saving.
        floats = []
        if len(self.headers) == 1:
            for index, offsets in self.float_edits.items():
                for offset in offsets:
                    absolute = self.resources[index].offsets[0] + offset
                    value = struct.unpack_from("<f", candidate, absolute)[0]
                    if math.isfinite(value) and 1e-6 < abs(value) < 1e6:
                        floats.append(absolute)
            floats = sorted(set(floats))
        root = core.APP_DATA / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="decoder-", dir=root) as folder:
            folder = Path(folder)
            stock, edited, output = (folder / name for name in ("stock.bin", "edited.bin", "sealed.bin"))
            stock.write_bytes(self.plain)
            edited.write_bytes(candidate)
            cmd = [sys.executable, str(core.ROOT / "lua_runner.py"), str(stock), str(edited), str(output),
                   ",".join(map(str, floats))]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode or not output.is_file():
                raise ValueError("Hash correction could not produce a valid file. No output was exported.\n" +
                                 (result.stdout + result.stderr)[-1200:])
            sealed = output.read_bytes()
        verified = core.unseal(sealed)
        if len(verified) != len(self.plain) or blocks(verified) != self.headers or content_hash(verified) != content_hash(self.plain):
            raise ValueError("Repacked data failed structure/content-hash verification.")
        allowed = set()
        for pos, _, _ in self.headers:
            allowed.update(range(pos + 17, pos + 24))
        adjustments = []
        for offset in floats:
            allowed.update(range(offset, offset + 4))
            if candidate[offset:offset + 4] != verified[offset:offset + 4]:
                requested, actual = struct.unpack_from("<f", candidate, offset)[0], struct.unpack_from("<f", verified, offset)[0]
                adjustments.append(f"0x{offset:X}: {requested:.9g} -> {actual:.9g}")
        if any(a != b and index not in allowed for index, (a, b) in enumerate(zip(candidate, verified))):
            raise ValueError("Hash correction changed unexpected payload bytes; export refused.")
        return sealed, adjustments

    def save(self, filename, sealed):
        target = Path(filename)
        if target.resolve() == self.path.resolve():
            raise ValueError("Choose a new folder to preserve the input file.")
        atomic_write(target, sealed)
        return [target]
