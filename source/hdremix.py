"""Native adaptation of the supplied HD REMIX 0.5.4 cosmetic profiles (GPL-3.0).

Original source and complete notices are in vendor/hdremix052. The upstream
standalone installer's game-file ownership/legacy cleanup is not invoked.
"""
import hashlib
import json
import struct
import math
from pathlib import Path

import core
from portable_hash import finish_armor, content_hash

ROOT = Path(__file__).resolve().parent / 'vendor' / 'hdremix052'
CATALOG = json.loads((ROOT / 'Source' / 'Profiles.json').read_text(encoding='utf-8-sig'))
SCHEMA = json.loads((ROOT / 'Source' / 'Schema.json').read_text(encoding='utf-8-sig'))
ARMOR = 'generated_customization_armor_sets.dl_bin'
KIT = 0xD9A55AA0
PADDING_IDS = (0x250FD6C1, 0x1D0E3431, 0x708451E9, 0xD59566D5, 0x1369B95B)


def armor_headers(data):
    if len(data) < 4:
        raise ValueError('Truncated armour catalog.')
    count = struct.unpack_from('<I', data)[0]
    if not 0 < count <= 4096:
        raise ValueError('Unsupported armour record count.')
    pos, headers, ids = 4, [], set()
    def array(payload, size, descriptor, stride, maximum):
        if descriptor < payload or descriptor + 16 > payload + size:
            raise ValueError('Armour array descriptor out of bounds.')
        relative, length, reserved = struct.unpack_from('<QII', data, descriptor)
        if length > maximum or reserved:
            raise ValueError('Unsupported armour array count/reserved value.')
        if not length:
            if relative not in (0, (1<<64)-1) and relative > size:
                raise ValueError('Invalid empty armour array.')
            return payload, 0
        if relative < 64 or relative + length * stride > size:
            raise ValueError('Armour array payload out of bounds.')
        return payload + relative, length
    for _ in range(count):
        if pos + 24 > len(data) or data[pos:pos+8] != b'LDLD\x01\0\0\0':
            raise ValueError('Unsupported armour LDLD header.')
        kind, size = struct.unpack_from('<II', data, pos+8)
        payload = pos + 24
        if kind != KIT or size < 64 or payload + size > len(data) or data[pos+16] != 1:
            raise ValueError('Unsupported armour layout.')
        definition = struct.unpack_from('<I', data, payload)[0]
        if definition in ids:
            raise ValueError('Duplicate armour definition.')
        ids.add(definition)
        body, n = array(payload, size, payload+48, 24, 8)
        for i in range(n):
            pieces, m = array(payload, size, body+i*24+8, 112, 64)
            for j in range(m):
                array(payload, size, pieces+j*112+96, 16, 64)
        headers.append((pos, kind, size))
        pos = payload + size
    if pos != len(data):
        raise ValueError('Unexpected armour trailing data.')
    return headers


def patch_armor(sealed, mask=63, padding=False, log=lambda s: None):
    if mask < 0 or mask & ~63:
        raise ValueError('Invalid unlock category mask.')
    original = core.unseal(sealed)
    headers = armor_headers(original)
    by_id = {struct.unpack_from('<I', original, p+24)[0]: p+24 for p,_,_ in headers}
    edits = {e['definition']: e for e in SCHEMA['changes']}
    changed = bytearray(original)
    found = 0
    for group in CATALOG['groups']:
        selected = bool(group['bit'] & mask)
        for item in group['items']:
            edit = edits[item['definition']]
            payload = by_id.get(item['definition'])
            if payload is None:
                if selected:
                    log('Unlock profile target absent: ' + item['name'])
                continue
            current = struct.unpack_from('<I', original, payload+4)[0]
            if current not in (edit['before_tag'], edit['after_tag']):
                if selected:
                    raise ValueError('Conflicting availability edit for ' + item['name'])
                continue
            if selected:
                found += 1
            struct.pack_into('<I', changed, payload+4, edit['after_tag'] if selected else edit['before_tag'])
    if mask and not found:
        raise ValueError('No selected unlock definitions match the captured armour catalog.')
    for definition in PADDING_IDS:
        payload = by_id.get(definition)
        if payload is None:
            if padding:
                raise ValueError('Colored B-01 definition missing.')
            continue
        category = struct.unpack_from('<I', original, payload+40)[0]
        current = struct.unpack_from('<I', original, payload+28)[0]
        if category or (current not in (0,1) and padding):
            raise ValueError('Unsupported or conflicting colored B-01 passive.')
        if current in (0,1):
            struct.pack_into('<I', changed, payload+28, int(padding))
    plain = finish_armor(original, changed, headers)
    if content_hash(plain) != content_hash(original):
        raise ValueError('Unlocker hash verification failed.')
    armor_headers(plain)
    result = sealed if plain == original else core.seal(plain)
    if core.unseal(result) != plain:
        raise ValueError('Unlocker encryption verification failed.')
    log(f'HD REMIX 0.5.4: {found} selected definitions present; output verified.')
    return result


def validate_stock(stock_folder, padding=False):
    stock_folder = Path(stock_folder)
    if padding:
        from dlbin_codec import DLBin
        passive = DLBin.open(stock_folder / 'generated_customization_passive_bonuses.dl_bin')
        if (len(passive.plain)<4 or struct.unpack_from('<I',passive.plain)[0] != len(passive.headers)
                or not 0<len(passive.headers)<=512 or passive.headers[0][0]!=4
                or passive.headers[-1][0]+24+passive.headers[-1][2]!=len(passive.plain)
                or any(a[0]+24+a[2]!=b[0] for a,b in zip(passive.headers,passive.headers[1:]))):
            raise ValueError('Unsupported native passive table layout.')
        valid = False
        found = False
        for resource in passive.resources:
            if resource.type_hash != 0x63CE0FEB:
                continue
            data = passive.payload(resource.index,0)
            if len(data) < 56 or struct.unpack_from('<I',data)[0] != 1:
                continue
            if found:
                raise ValueError('Duplicate native Extra Padding passive.')
            found = True
            pointer, count = struct.unpack_from('<QQ',data,16)
            if struct.unpack_from('<I',data,4)[0] != 4207037112 or not 0 < count <= 256 or pointer < 56 or pointer+count*16 > len(data):
                raise ValueError('Unsupported native Extra Padding passive.')
            valid = any(struct.unpack_from('<I',data,pointer+i*16)[0] == 2947431239 and
                        struct.unpack_from('<I',data,pointer+i*16+4)[0] == 1 and
                        math.isfinite(struct.unpack_from('<f',data,pointer+i*16+8)[0]) and
                        struct.unpack_from('<f',data,pointer+i*16+8)[0] > 0 for i in range(count))
        if not valid:
            raise ValueError('Native Extra Padding armour modifier could not be verified.')


def build_mod(cfg, log):
    stock = core.STOCK / ARMOR
    padding = bool(cfg.get('unlock_padding', False))
    validate_stock(core.STOCK, padding)
    output = patch_armor(stock.read_bytes(), int(cfg.get('unlock_groups',63)), padding, log)
    destination = core.APP_DATA / 'builtin' / 'hdremix052'
    destination.mkdir(parents=True,exist_ok=True)
    # The stock seed makes this target participate in the normal merge. Apply
    # semantic unlock edits after merging, preserving other mods' unrelated edits.
    core.atomic_write(destination / ARMOR, stock.read_bytes())
    return core.parse_mod(destination)
