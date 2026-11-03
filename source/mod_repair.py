"""Conservative three-way repair. No fuzzy matches or global hash substitution."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import struct
from pathlib import Path
import uuid

from archive_codec import Archive, SUFFIXES
from dlbin_codec import DLBin, content_hash


def open_file(path):
    return DLBin.open(path) if str(path).lower().endswith('.dl_bin') else Archive.open(path)


def snapshot(paths, destination):
    """Archive selected supported main files and sidecars in a new directory."""
    files = {}
    for path in paths:
        parsed = open_file(path)  # Validate before creating the snapshot.
        components = [(parsed.path, parsed.sealed)] if isinstance(parsed, DLBin) else [
            (Path(str(parsed.path) + suffix), blob) for suffix, blob in zip(SUFFIXES, parsed.blobs)
            if not suffix or Path(str(parsed.path) + suffix).exists()]
        for component, data in components:
            key = component.name.lower()
            if key in files and files[key][0].resolve() != component.resolve():
                raise ValueError('Selected files have duplicate names. Capture them separately.')
            files[key] = (component, data)
    if not files:
        raise ValueError('Select at least one supported file.')
    root = Path(destination) / ('repair-snapshot-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                                + '-' + uuid.uuid4().hex[:8])
    root.mkdir(parents=True, exist_ok=False)
    manifest = {'version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(), 'files': {}}
    for component, data in files.values():
        (root / component.name).write_bytes(data)
        manifest['files'][component.name] = hashlib.sha256(data).hexdigest()
    (root / 'snapshot.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return root


def verify_snapshot(path):
    path = Path(path)
    manifest_path = path.parent / 'snapshot.json'
    if not manifest_path.is_file():
        raise ValueError('Choose an old clean file inside a saved repair snapshot.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or path.name not in manifest.get('files', {}):
        raise ValueError('File is not listed in this snapshot.')
    for suffix in ('',) if path.suffix.lower() == '.dl_bin' else SUFFIXES:
        component = Path(str(path) + suffix)
        expected = manifest['files'].get(component.name)
        if expected is None:
            if component.exists():
                raise ValueError('Unexpected snapshot sidecar: ' + component.name)
            continue
        if not component.is_file() or hashlib.sha256(component.read_bytes()).hexdigest() != expected:
            raise ValueError('Snapshot integrity check failed: ' + component.name)


def transplant(old, new, mod):
    """Relocate changed 4-byte words using unique unchanged surrounding bytes."""
    if mod == old:
        return new, []
    if len(mod) != len(old):
        if new == old:
            return mod, ['Payload resized; stock payload is unchanged.']
        raise ValueError('Both stock layout and mod length changed; schema-aware repair is required.')
    changes = []
    for offset in range(0, len(old), 4):
        width = min(4, len(old) - offset)
        if old[offset:offset+width] != mod[offset:offset+width]:
            if changes and changes[-1][0] + changes[-1][1] == offset:
                start, length = changes[-1]
                changes[-1] = (start, length + width)
            else:
                changes.append((offset, width))
    result = bytearray(new)
    occupied = set()
    report = []
    for offset, width in changes:
        if new == old:
            target = offset
        else:
            target = None
            for context in (64, 32, 16, 8):
                before, after = old[max(0, offset-context):offset], old[offset+width:offset+width+context]
                if len(before) + len(after) < 16:
                    continue
                candidates = []
                start = 0
                anchor = before or after
                while True:
                    found = new.find(anchor, start)
                    if found < 0:
                        break
                    start = found + 1
                    pos = found + len(before) if before else found - width
                    if (pos >= len(before) and pos + width + len(after) <= len(new)
                            and new[pos-len(before):pos] == before
                            and new[pos+width:pos+width+len(after)] == after):
                        candidates.append(pos)
                        if len(candidates) > 1:
                            break
                if len(candidates) == 1:
                    target = candidates[0]
                    break
            if target is None:
                raise ValueError(f'0x{offset:X}: signature is missing or ambiguous.')
        current = new[target:target+width]
        requested = mod[offset:offset+width]
        if current not in (old[offset:offset+width], requested):
            raise ValueError(f'0x{offset:X}: game update and mod change the same field.')
        positions = set(range(target, target+width))
        if occupied & positions:
            raise ValueError('Relocated edits overlap.')
        occupied.update(positions)
        result[target:target+width] = requested
        report.append(f'0x{offset:X} -> 0x{target:X} ({width} bytes)')
    return bytes(result), report


def _key(resource, dlbin):
    return resource.type_hash if dlbin else (resource.name_hash, resource.type_hash)


def normalized_mod(old, mod):
    """Remove only a byte-for-byte reproducible trailing hash-correction word."""
    if len(old.plain) == len(mod.plain):
        return mod, False
    from portable_hash import finish_tail
    if len(old.headers) != len(mod.headers) or old.headers[:-1] != mod.headers[:-1]:
        raise ValueError('Changed block layout is not a recognized hash-correction footer.')
    last, kind, size = old.headers[-1]
    if (last + 24 + size != len(old.plain) or mod.headers[-1][:2] != (last, kind)
            or mod.headers[-1][2] - size != len(mod.plain) - len(old.plain)
            or len(mod.plain) != ((len(old.plain) + 7) & ~7) + 8):
        raise ValueError('Unrecognized payload extension; a schema migration is required.')
    candidate = bytearray(mod.plain[:len(old.plain)])
    struct.pack_into('<I', candidate, last + 12, size)
    if finish_tail(old.plain, candidate, old.headers) != mod.plain:
        raise ValueError('Trailing bytes do not match the canonical hash-correction footer.')
    # Construct a separate view; the supplied mod and its hash identity stay intact.
    import core
    return DLBin(mod.path, core.seal(bytes(candidate))), True


def match_block(document, resource, payload):
    """Repeated types require exact identity or two independent unique anchors."""
    candidates = [r for r in document.resources if r.type_hash == resource.type_hash]
    if document.path.name.lower() == 'generated_customization_armor_sets.dl_bin' and resource.type_hash == 0xD9A55AA0:
        # Armour kits carry a unique definition ID. Validate the complete
        # table/arrays before using that identity; short repeated kit payloads
        # cannot always provide two independent byte anchors.
        import hdremix
        hdremix.armor_headers(document.plain)
        if len(payload) < 64:
            raise ValueError('Truncated armour kit identity.')
        identity = struct.unpack_from('<I', payload)[0]
        matches = [r for r in candidates if struct.unpack_from('<I', document.payload(r.index, 0))[0] == identity]
        if len(matches) != 1:
            raise ValueError('Armour definition is missing or duplicated in current stock.')
        return matches[0]
    exact = [r for r in candidates if document.payload(r.index, 0) == payload]
    if len(exact) == 1:
        return exact[0]
    if len(candidates) == 1:
        return candidates[0]
    votes = Counter()
    anchors = set()
    # Distinct nonoverlapping 32-byte samples, spread over the whole block.
    slots = len(payload) // 32
    positions = sorted({(i * (slots-1) // 15) * 32 for i in range(16)}) if slots else []
    for offset in positions:
        anchor = payload[offset:offset+32]
        if anchor in anchors or len(set(anchor)) < 4:
            continue
        anchors.add(anchor)
        found = [r for r in candidates if anchor in document.payload(r.index, 0)]
        if len(found) == 1:
            votes[found[0].index] += 1
    strong = [index for index, count in votes.items() if count >= 2]
    if len(strong) != 1 or any(index != strong[0] for index in votes):
        raise ValueError('Repeated block type has no unique identity supported by two independent anchors.')
    return document.resources[strong[0]]


def stratagem_flags(old, new, mod, schema_path):
    """Known 400-byte StratagemInfo layout: relocate declared flag bits by Id."""
    from game_schema import Library
    library = Library.open(schema_path)
    root = library.types.get(0x30EB6399)
    if (not root or root.name != 'StratagemSettings' or root.size != 16 or len(root.members) != 1
            or (root.members[0].atom, root.members[0].storage, root.members[0].offset) != (1, 20, 0)):
        raise ValueError('Installed StratagemSettings schema is not the supported array layout.')
    record = library.types.get(root.members[0].type_id)
    if (not record or record.name != 'StratagemInfo' or record.size != 400
            or not any((m.atom, m.storage, m.offset, m.size) == (0, 6, 4, 4) for m in record.members)
            or sum((m.atom, m.storage, m.offset, m.size) == (3, 4, 368, 1) for m in record.members) != 2):
        raise ValueError('Installed StratagemInfo schema does not match the verified ID/flag layout.')
    def records(data):
        if len(data) < 16:
            raise ValueError('Truncated stratagem array.')
        start, count = struct.unpack_from('<QQ', data)
        if start < 16 or start % 4 or count > 20000 or start + count*400 > len(data):
            raise ValueError('Stratagem array lies outside its payload.')
        result = {}
        for index in range(count):
            pos = start + index*400
            identity = struct.unpack_from('<I', data, pos+4)[0]
            if identity in result:
                raise ValueError('Duplicate stratagem record ID.')
            result[identity] = pos
        return result
    old_records, mod_records, new_records = map(records, (old, mod, new))
    if len(old) != len(mod) or old_records != mod_records:
        raise ValueError('Mod changes stratagem array shape or record identities.')
    allowed = {pos+368 for pos in old_records.values()}
    if any(a != b and (index not in allowed or (a ^ b) & ~3)
           for index, (a, b) in enumerate(zip(old, mod))):
        raise ValueError('Mod includes edits outside the verified stratagem flag bits.')
    result = bytearray(new)
    report = []
    for identity, pos in old_records.items():
        offset = pos + 368
        mask = old[offset] ^ mod[offset]
        if not mask:
            continue
        if identity not in new_records:
            raise ValueError(f'Edited stratagem {identity:08x} was removed from current stock.')
        target = new_records[identity] + 368
        result[target] = (new[target] & ~mask) | (mod[offset] & mask)
        report.append(f'Schema-checked stratagem {identity:08x} flags: 0x{offset:X} -> 0x{target:X}; bit mask {mask:02x}')
    return bytes(result), report


def analyse_data(old, new, mod, report):
    errors, pending, used_old, used_new = [], [], set(), set()
    if old.path.name.lower() == 'generated_customization_armor_sets.dl_bin':
        import hdremix
        for document in (old, new, mod):
            hdremix.armor_headers(document.plain)
    try:
        normalized, removed = normalized_mod(old, mod)
        if removed:
            report.append('Recognized and removed the old canonical hash-correction footer; current hash will be solved anew.')
    except ValueError as exc:
        return RepairPlan(old, new, mod, report + ['BLOCKED: ' + str(exc)], [str(exc)])
    if len(old.resources) != len(normalized.resources):
        return RepairPlan(old, new, mod, report + ['BLOCKED: Mod adds or removes blocks.'], ['Mod adds or removes blocks.'])
    for resource in normalized.resources:
        payload = normalized.payload(resource.index, 0)
        label = f'Block {resource.index} / type {resource.type_hash:08x}'
        try:
            source = match_block(old, resource, payload)
            if source.index in used_old:
                raise ValueError('More than one mod block maps to the same old block.')
            used_old.add(source.index)
            original = old.payload(source.index, 0)
            if original == payload:
                continue
            target = match_block(new, source, original)
            if target.index in used_new:
                raise ValueError('More than one mod block maps to the same current block.')
            used_new.add(target.index)
            try:
                repaired, moves = transplant(original, new.payload(target.index, 0), payload)
            except ValueError:
                schema = new.path.parent / 'dl_library.dl_typelib'
                if new.path.name.lower() != 'generated_stratagem_settings.dl_bin' or resource.type_hash != 0x30EB6399 or not schema.is_file():
                    raise
                repaired, moves = stratagem_flags(original, new.payload(target.index, 0), payload, schema)
            if len(repaired) != target.sizes[0]:
                raise ValueError('Gameplay payload resizing requires a schema migration.')
            pending.append((target.index, repaired))
            report.append(f'{label} -> current block {target.index}; payload offsets {source.offsets[0]:X} -> {target.offsets[0]:X}')
            report.extend(f'{label}: {move}' for move in moves)
        except ValueError as exc:
            errors.append(f'{label}: {exc}')
    if not pending and not errors:
        errors.append('No transferable mod payload changes were found.')
    if errors:
        report.extend('BLOCKED: ' + error for error in errors)
        report.append('Export blocked. No partial repair will be saved.')
    else:
        for index, payload in pending:
            new.replace(index, 0, payload)
        report.append(f'Ready: {len(pending)} changed block(s). Exact payload preservation and current hash verification required on export.')
        report.append('Data-only export: installer/runtime packaging is not reproduced. A packaging-related break may still require a compatible installer.')
    return RepairPlan(old, new, mod, report, errors)


def analyse(old_path, new_path, mod_path):
    verify_snapshot(old_path)
    old, new, mod = map(open_file, (old_path, new_path, mod_path))
    dlbin = isinstance(old, DLBin)
    if any(isinstance(item, DLBin) != dlbin for item in (new, mod)):
        raise ValueError('All three inputs must belong to the same file family.')
    if dlbin and not (old.path.name.lower() == new.path.name.lower() == mod.path.name.lower()):
        raise ValueError('Select the same generated data filename from all three versions.')
    report = ['Three-way comparison: old clean -> current clean + mod edits.',
              'Offsets below are relative to each resource payload.']
    if dlbin:
        report.append(f'Stock content hash: {content_hash(old.plain):016x} -> {content_hash(new.plain):016x}')
        return analyse_data(old, new, mod, report)
    errors = []
    old_keys = Counter(_key(r, dlbin) for r in old.resources)
    mod_keys = Counter(_key(r, dlbin) for r in mod.resources)
    new_keys = Counter(_key(r, dlbin) for r in new.resources)
    pending = []
    used = set()
    for resource in mod.resources:
        key = _key(resource, dlbin)
        label = f'Block type {key:08x}' if dlbin else f'Resource {key[0]:016x}/{key[1]:016x}'
        try:
            if old_keys[key] != 1 or mod_keys[key] != 1:
                raise ValueError('Old/mod identity missing or duplicated; cannot identify edits.')
            source = next(r for r in old.resources if _key(r, dlbin) == key)
            sections = range(1 if dlbin else 3)
            if all(old.payload(source.index, s) == mod.payload(resource.index, s) for s in sections):
                continue
            candidates = [r for r in new.resources if _key(r, dlbin) == key]
            if not candidates and not dlbin:
                # A renamed ID can be proved only by an exact, unique payload triplet.
                candidates = [r for r in new.resources if all(
                    old.payload(source.index, s) == new.payload(r.index, s) for s in range(3))]
            if len(candidates) != 1:
                raise ValueError('Current identity is missing or ambiguous; no proven hash mapping.')
            target = candidates[0]
            if new_keys[_key(target, dlbin)] != 1 or target.index in used:
                raise ValueError('Multiple resources map to the same current identity.')
            used.add(target.index)
            report.append(f'{label}: stock payload offsets {source.offsets} -> {target.offsets}')
            if not dlbin and _key(target, False) != key:
                report.append(f'{label}: hash mapping -> {target.name_hash:016x}/{target.type_hash:016x}')
            for section in sections:
                payload, moves = transplant(old.payload(source.index, section), new.payload(target.index, section),
                                            mod.payload(resource.index, section))
                if moves:
                    pending.append((target.index, section, payload))
                    report.extend(f'{label} / {section}: {move}' for move in moves)
        except ValueError as exc:
            errors.append(f'{label}: {exc}')
    # Missing blocks in data files mean a different layout, rather than a subset patch.
    if dlbin and old_keys != mod_keys:
        errors.append('Old data and mod block identities differ.')
    if not pending and not errors:
        errors.append('No transferable mod payload changes were found.')
    report.extend('BLOCKED: ' + error for error in errors)
    if errors:
        report.append('Export blocked. No partial repair will be saved.')
    else:
        for index, section, payload in pending:
            new.replace(index, section, payload)
        report.append(f'Ready: {len(pending)} changed payload section(s).')
        if dlbin:
            report.append(f'Export targets current content hash {content_hash(new.plain):016x}; resealing must pass verification.')
        report.append('Embedded IDs/pointers and schema changes are not inferred. Test the export in-game.')
    return RepairPlan(old, new, mod, report, errors)


class RepairPlan:
    def __init__(self, old, current, mod, report, errors):
        self.old, self.current, self.mod = old, current, mod
        self.report, self.errors = report, errors

    def export(self, folder):
        if self.errors:
            raise ValueError('Resolve blocked matches before export.')
        folder = Path(folder).resolve()
        if any(folder == item.path.parent.resolve() for item in (self.old, self.current, self.mod)):
            raise ValueError('Choose a separate output folder to preserve all inputs.')
        name = self.current.path.name
        if isinstance(self.current, Archive):
            # The current archive ID determines the installation target.
            name = name.split('.patch_')[0] + '.patch_0'
        target = folder / name
        if any(Path(str(target) + suffix).exists() for suffix in SUFFIXES):
            raise ValueError('Output already exists. Choose an empty output folder.')
        if isinstance(self.current, DLBin):
            sealed, adjustments = self.current.prepare()
            if adjustments:
                raise ValueError('Exact repair requires value changes; automatic export refused.')
            return self.current.save(target, sealed)
        return self.current.export(target)
