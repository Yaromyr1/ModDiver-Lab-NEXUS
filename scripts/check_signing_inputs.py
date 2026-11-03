"""Verify the Nexus dependency lock and require reviewed eligibility for signing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_release


def inventory():
    result = []
    for current, dirs, files in os.walk(build_release.SOURCE):
        ignored = build_release._nexus_source_ignore(current, dirs + files)
        dirs[:] = sorted(d for d in dirs if d not in ignored)
        for name in sorted(files):
            if name in ignored:
                continue
            path = Path(current) / name
            if path.suffix.lower() not in {'.exe', '.dll', '.pyd'}:
                continue
            data = path.read_bytes()
            result.append(dict(path=path.relative_to(build_release.SOURCE).as_posix(),
                               size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return sorted(result, key=lambda item: item['path'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true', help='Review and commit changed hashes; never run automatically in release CI')
    parser.add_argument('--signing', action='store_true')
    args = parser.parse_args()
    lock = ROOT / 'signing/dependency-lock.json'
    actual = inventory()
    if args.record:
        lock.write_text(json.dumps(actual, indent=2) + '\n', encoding='utf-8')
        print('Recorded', len(actual), 'Nexus PE inputs. Hashes do not establish upstream provenance.')
        return
    if actual != json.loads(lock.read_text(encoding='utf-8')):
        raise SystemExit('Nexus dependency bytes changed. Review upstream provenance before updating the lock.')
    if args.signing:
        review = json.loads((ROOT / 'signing/readiness.json').read_text(encoding='utf-8'))
        for key in ('license_audit_complete', 'upstream_provenance_verified', 'privacy_review_complete',
                    'mfa_confirmed', 'foundation_approved', 'modified_python_approved', 'ci_build_validated'):
            if review.get(key) is not True:
                raise SystemExit('Signing is not ready: ' + key)
        if not (ROOT / 'LICENSE').is_file():
            raise SystemExit('Missing project LICENSE.')
    print('Verified', len(actual), 'locked Nexus PE inputs.')


if __name__ == '__main__':
    main()
