"""Named gameplay changes exported through HellForge's checked stats format."""
import json
import math
from pathlib import Path
import tempfile
import uuid
import zipfile

CATEGORIES = ('weapons', 'throwables', 'backpacks', 'vehicles', 'stratagems', 'helldiver',
              'boosters', 'perks', 'projectiles', 'damage', 'explosions', 'statuses',
              'enemies', 'difficulty', 'rosters', 'compositions')


def _bad_constant(value):
    raise ValueError('Values must be finite numbers.')


def read(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=_bad_constant)
    validate(doc)
    return doc


def value(text):
    result = json.loads(text, parse_constant=_bad_constant)
    def finite(v):
        if isinstance(v, list):
            return all(finite(i) for i in v)
        return isinstance(v, (int, float, bool)) and (not isinstance(v, float) or math.isfinite(v))
    if not finite(result):
        raise ValueError('Enter a number, true/false, or a list of numbers such as [4,4,4,4].')
    return result


def validate(doc):
    if not isinstance(doc, dict) or doc.get('format') != 1:
        raise ValueError('Choose a HellForge stats file with format 1.')
    unknown = set(doc) - {'format', 'raw', *CATEGORIES}
    if unknown:
        raise ValueError('Unsupported stats categories: ' + ', '.join(sorted(unknown)))
    for category in CATEGORIES:
        rows = doc.get(category, {})
        if not isinstance(rows, dict):
            raise ValueError('Invalid stats category: ' + category)
        for target, fields in rows.items():
            if not isinstance(target, str) or not target.strip() or not isinstance(fields, dict):
                raise ValueError('Each stats entry needs a target and named fields.')
            for field, item in fields.items():
                if not isinstance(field, str) or not field.strip():
                    raise ValueError('Each stat needs a field name.')
                value(json.dumps(item, allow_nan=False))
    if 'raw' in doc and not isinstance(doc['raw'], list):
        raise ValueError('Invalid raw stats list.')


def export(root, doc, name, destination):
    import core
    import hellforge
    validate(doc)
    name = str(name).strip()
    if not name:
        raise ValueError('Enter a name for the mod.')
    if not any(doc.get(k) for k in (*CATEGORIES, 'raw')):
        raise ValueError('Add at least one stat change before exporting.')
    destination = Path(destination).resolve()
    if destination == Path(root).resolve() or destination.is_relative_to(Path(root).resolve()):
        raise ValueError('Save the ZIP outside HellForge, then add it through Mod Library.')
    manifest = {'format': 1, 'id': 'moddiver.stats-' + uuid.uuid5(uuid.NAMESPACE_URL, name).hex[:24],
                'name': name, 'version': '1.0.0', 'gameplay': True}
    with tempfile.TemporaryDirectory(prefix='moddiver-stats-') as temp:
        folder = Path(temp)
        for filename, data in (('hellforge-mod.json', manifest), ('hellforge-stats.json', doc)):
            (folder / filename).write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
        report = hellforge._run(Path(root), 'check-stats', '--mod', str(folder))
        # Only replace a prior export after HellForge accepted every change.
        output = folder / 'export.zip'
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for filename in ('hellforge-mod.json', 'hellforge-stats.json'):
                archive.write(folder / filename, filename)
        core.atomic_write(destination, output.read_bytes())
    return report
