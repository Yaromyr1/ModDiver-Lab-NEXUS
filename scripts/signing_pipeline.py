"""Prepare signing inputs and repackage a verified signed launcher.

Never signs third-party components and never publishes a release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import struct
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_release


def stage(package, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        # Extract only the fixed signing target; never interpret ZIP paths.
        data = archive.read(build_release.LEGACY_EXE_PATH)
    target = destination / 'ModDiver Laboratory.exe'
    target.write_bytes(data)
    return target


def finish(package, signed_exe, output):
    """Caller must verify Authenticode before invoking this function."""
    signed = Path(signed_exe).read_bytes()
    output = Path(output)
    if Path(package).resolve() == output.resolve():
        raise ValueError('Keep the unsigned input intact; use a separate output.')
    output.parent.mkdir(parents=True, exist_ok=True)
    target = build_release.LEGACY_EXE_PATH
    sums = 'ModDiver Laboratory/SHA256SUMS.txt'
    with zipfile.ZipFile(package) as source:
        if target not in source.namelist() or sums not in source.namelist():
            raise ValueError('Not a ModDiver Windows release package.')
        # Permit only Authenticode's checksum/security-directory/certificate edits.
        original = source.read(target)
        if unsigned_content(original) != unsigned_content(signed):
            raise ValueError('Signed EXE differs from the unsigned build beyond signature fields.')
        lines = []
        with zipfile.ZipFile(output, 'w') as archive:
            for info in source.infolist():
                if info.filename == sums:
                    continue
                content = signed if info.filename == target else source.read(info)
                archive.writestr(info, content)
                # Match original manifest convention (manifest itself is hashed).
                lines.append(hashlib.sha256(content).hexdigest() + '  ' +
                             info.filename.removeprefix('ModDiver Laboratory/'))
            archive.writestr(sums, '\r\n'.join(lines) + '\r\n')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(
        digest + '  ' + output.name + '\n', encoding='ascii')
    return output


def unsigned_content(data):
    content = bytearray(data)
    if content[:2] != b'MZ':
        raise ValueError('Not a PE executable.')
    pe = struct.unpack_from('<I', content, 0x3c)[0]
    if content[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE signature.')
    optional = pe + 24
    magic = struct.unpack_from('<H', content, optional)[0]
    if magic not in (0x10b, 0x20b):
        raise ValueError('Unsupported PE format.')
    directory = optional + (96 if magic == 0x10b else 112) + 8 * 4
    offset, size = struct.unpack_from('<II', content, directory)
    content[optional+64:optional+68] = b'\0' * 4
    content[directory:directory+8] = b'\0' * 8
    if offset or size:
        if offset < directory + 8 or size < 8 or offset + size != len(content):
            raise ValueError('Unexpected certificate table layout.')
        del content[offset:]
    # Authenticode pads an unsigned file to an eight-byte boundary.
    content.extend(b'\0' * (-len(content) % 8))
    return bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('stage')
    prepare.add_argument('package', type=Path)
    prepare.add_argument('destination', type=Path)
    complete = sub.add_parser('finish')
    complete.add_argument('package', type=Path)
    complete.add_argument('signed_exe', type=Path)
    complete.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'stage':
        print(stage(args.package, args.destination))
    else:
        # Enforce Windows signature validation even when invoked outside CI.
        import subprocess
        command = "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:MODDIVER_SIGNED_EXE; if($s.Status -ne 'Valid'){throw ('Invalid signature: '+$s.Status)}"
        shell = shutil.which('pwsh') or shutil.which('powershell.exe')
        if not shell:
            raise SystemExit('Windows PowerShell signature verification is required.')
        subprocess.run([shell, '-NoProfile', '-Command', command], check=True,
                       env=dict(os.environ, MODDIVER_SIGNED_EXE=str(args.signed_exe.resolve())))
        print(finish(args.package, args.signed_exe, args.output))


if __name__ == '__main__':
    main()
