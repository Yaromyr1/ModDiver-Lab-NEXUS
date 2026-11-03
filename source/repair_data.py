"""Offline Nexus helpers; repair references come from captured Steam stock."""
import hashlib
from pathlib import Path

def directory_digest(folder):
    digest = hashlib.sha256()
    total = 0
    folder = Path(folder)
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = path.relative_to(folder).as_posix().encode("utf-8")
        data = path.read_bytes()
        total += len(data)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return total, digest.hexdigest()

def packages(folder, cache=None, *, download=False, progress=lambda message: None):
    return []

def prefetch(folder, destination, *, progress=lambda message: None):
    return packages(folder, destination)
