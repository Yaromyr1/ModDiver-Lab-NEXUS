"""Offline version and pointer helpers required by the Linux bootstrap."""
import os
import re
import uuid
from pathlib import Path

POINTER_NAME = "current.txt"
OK_MARKER = ".app-ok"
_SAFE_FOLDER = re.compile(r"\d+(?:\.\d+)*(?:-rollback-[0-9a-f]{8})?\Z")

class UpdateError(RuntimeError):
    pass

def _parts(value):
    text = str(value or "").split("-rollback-", 1)[0]
    if not re.fullmatch(r"[vV]?\d+(?:\.\d+)*", text):
        raise UpdateError("Unrecognized version: " + repr(value))
    return tuple(int(part) for part in text.lstrip("vV").split("."))

def canonical_version(value):
    return ".".join(str(part) for part in _parts(value))

def _is_newer(candidate, current):
    left, right = _parts(candidate), _parts(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))

def read_pointer(app_root):
    try:
        lines = (Path(app_root) / POINTER_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    found = [line.strip() for line in lines if _SAFE_FOLDER.fullmatch(line.strip())]
    return (found[0] if found else None), (found[1] if len(found) > 1 else None)

def _write_pointer(app_root, current, previous):
    app_root = Path(app_root)
    target = app_root / POINTER_NAME
    temp = app_root / ("." + POINTER_NAME + "." + uuid.uuid4().hex[:8] + ".tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(current + "\n" + (previous + "\n" if previous else ""))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp), str(target))
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
