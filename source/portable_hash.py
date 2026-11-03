"""Platform-independent LDLD hash correction; formulas derived from SHODAN/HD REMIX (GPL-3.0).

HD REMIX source and copyright/license notices are included in vendor/hdremix052.
Padding correction is restricted by callers to the validated armour-kit layout
or the explicitly opted-in experimental schema footer path.
"""
import struct
import hashlib
from collections import OrderedDict

MASK = (1 << 64) - 1
M = 0xC6A4A7935BD1E995
INV = 0x5F7A0EA7E59B19BD
SEED = 0xDEADBEEFABAD1DEA
_HASH_CACHE = OrderedDict()


def shift(v):
    return v ^ (v >> 47)


def mix(v):
    return shift(v * M & MASK) * M & MASK


def unmix(v):
    return shift(v * INV & MASK) * INV & MASK


def forward(state, data, start, end):
    # iter_unpack avoids a Python call and offset lookup for every eight bytes.
    for (word,) in struct.iter_unpack('<Q', memoryview(data)[start:end]):
        word = word * M & MASK
        word ^= word >> 47
        word = word * M & MASK
        state = (state ^ word) * M & MASK
    return state


def backward(state, data, start, end):
    for offset in range(end - 8, start - 1, -8):
        state = (state * INV & MASK) ^ mix(struct.unpack_from('<Q', data, offset)[0])
    return state


def content_hash(data):
    # Repeated repair verification sees the same large plaintext many times.
    # Cache by its full SHA-256, never by file timestamps or mutable object IDs.
    # Retain only small digests/results, not copies of 47+ MB game files.
    key = (len(data), hashlib.sha256(data).digest())
    cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    end = len(data) & ~7
    state = forward((SEED ^ (len(data) * M)) & MASK, data, 0, end)
    if end < len(data):
        state = (state ^ int.from_bytes(data[end:], 'little')) * M & MASK
    result = shift(shift(state) * M & MASK)
    _HASH_CACHE[key] = result
    if len(_HASH_CACHE) > 32:
        _HASH_CACHE.popitem(last=False)
    return result


def correct_reserved(original, candidate, headers):
    """Solve in reserved header bytes only. None means this layout needs another solver."""
    target = content_hash(original)
    if content_hash(candidate) == target:
        return bytes(candidate)
    aligned = [pos for pos, _, _ in headers if pos % 8 == 0]
    if not aligned or len(headers) < 2:
        return None
    data = bytearray(candidate)
    for pos, _, _ in headers:
        data[pos + 16:pos + 24] = b'\x01' + b'\0' * 7
    x = aligned[-1]
    first, stop = x + 16, x + 24
    whole = len(data) & ~7
    final = shift(shift(target) * INV & MASK)
    if whole < len(data):
        final = (final * INV & MASK) ^ int.from_bytes(data[whole:], 'little')
    start = (SEED ^ (len(data) * M)) & MASK
    salts = sorted((p for p, _, _ in headers if p != x), key=lambda p: abs(p-x))
    for pos in salts:
        lo, hi = (pos + 17) & ~7, ((pos + 18) & ~7) + 8
        if hi <= first:
            prefix = forward(start, data, 0, lo)
            suffix = backward(final, data, stop, whole)
        elif lo >= stop:
            prefix = forward(start, data, 0, first)
            suffix = backward(final, data, hi, whole)
        else:
            continue
        for salt in range(65536):
            struct.pack_into('<H', data, pos + 17, salt)
            before = forward(prefix, data, lo, first) if hi <= first else prefix
            after = suffix if hi <= first else backward(suffix, data, stop, hi)
            word = unmix(before ^ (after * INV & MASK))
            if word & 255 == 1:
                struct.pack_into('<Q', data, first, word)
                if content_hash(data) != target:
                    raise ValueError('Reserved-byte hash correction failed verification.')
                return bytes(data)
        data[pos+17:pos+19] = b'\0\0'
    return None


def finish_armor(original, candidate, headers):
    """HD REMIX trailing correction for a validated, contiguous armour-kit table."""
    if bytes(candidate) == original:
        return original
    corrected = correct_reserved(original, candidate, headers)
    if corrected is not None:
        return corrected
    last, kind, size = headers[-1]
    if kind != 0xD9A55AA0 or last + 24 + size != len(original) or len(candidate) != len(original):
        raise ValueError('Unsupported armour correction layout.')
    return finish_tail(original,candidate,headers)


def finish_tail(original,candidate,headers):
    """Append a correction word; callers must validate a variable-size schema first."""
    last,_,size=headers[-1]
    if last+24+size!=len(original) or len(candidate)!=len(original):
        raise ValueError('Unsupported trailing correction boundary.')
    offset = (len(candidate) + 7) & ~7
    output = bytearray(candidate) + bytearray(offset + 8 - len(candidate))
    struct.pack_into('<I', output, last+12, size + len(output) - len(original))
    state = forward((SEED ^ (len(output)*M)) & MASK, output, 0, offset)
    wanted = shift(shift(content_hash(original)) * INV & MASK)
    struct.pack_into('<Q', output, offset, unmix(state ^ (wanted * INV & MASK)))
    if content_hash(output) != content_hash(original):
        raise ValueError('Trailing hash correction failed verification.')
    return bytes(output)
