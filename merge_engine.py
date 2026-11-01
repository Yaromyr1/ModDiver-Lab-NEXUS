"""Safer byte-level merge helpers for ModDiver Laboratory.

This module deliberately does not pretend to understand undocumented game schemas.
It merges byte edits relative to a known stock baseline, reports collisions, and
fails closed when input lengths make offset-based merging unsafe.
"""
from __future__ import annotations

import os
import tempfile
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class MergeSafetyError(ValueError):
    """Raised when a binary merge cannot be performed safely."""


@dataclass(frozen=True)
class ByteRun:
    start: int
    end: int  # inclusive

    def overlaps(self, other: "ByteRun") -> bool:
        return self.start <= other.end and other.start <= self.end


@dataclass(frozen=True)
class Conflict:
    start: int
    end: int
    earlier_mod: str
    later_mod: str


@dataclass(frozen=True)
class OwnerInterval:
    """Inclusive byte range currently owned by the last mod that changed it."""
    start: int
    end: int
    owner: str


def _replace_owner_interval(owners: list[OwnerInterval], start: int, end: int,
                            owner: str) -> list[OwnerInterval]:
    """Replace byte ownership in a range, preserving and coalescing the rest."""
    updated: list[OwnerInterval] = []
    for interval in owners:
        if interval.end < start or interval.start > end:
            updated.append(interval)
            continue
        if interval.start < start:
            updated.append(OwnerInterval(interval.start, start - 1, interval.owner))
        if interval.end > end:
            updated.append(OwnerInterval(end + 1, interval.end, interval.owner))
    updated.append(OwnerInterval(start, end, owner))
    updated.sort(key=lambda interval: interval.start)

    coalesced: list[OwnerInterval] = []
    for interval in updated:
        if (coalesced and coalesced[-1].owner == interval.owner
                and coalesced[-1].end + 1 == interval.start):
            previous = coalesced[-1]
            coalesced[-1] = OwnerInterval(previous.start, interval.end, previous.owner)
        else:
            coalesced.append(interval)
    return coalesced


def diff_runs(stock: bytes, candidate: bytes) -> list[ByteRun] | None:
    """Return contiguous changed byte ranges; None means file lengths differ."""
    if len(stock) != len(candidate):
        return None
    runs: list[ByteRun] = []
    start = None
    for i, (a, b) in enumerate(zip(stock, candidate)):
        if a != b:
            if start is None:
                start = i
        elif start is not None:
            runs.append(ByteRun(start, i - 1))
            start = None
    if start is not None:
        runs.append(ByteRun(start, len(stock) - 1))
    return runs


def plan_merge(stock: bytes, mods: Sequence[tuple[str, bytes]], row_size: int = 0) -> tuple[bytes, list[Conflict]]:
    """Apply mods in order; later mods win overlapping bytes, with explicit conflicts.

    ``row_size`` enables field-aware reporting: two mods that change *different bytes*
    of the same fixed-size row (e.g. two fields of one weapon) are still a conflict,
    because a byte splice can leave a row the game does not expect.
    """
    prepared: list[tuple[str, bytes, list[ByteRun]]] = []
    for name, candidate in mods:
        runs = diff_runs(stock, candidate)
        if runs is None:
            raise MergeSafetyError(
                f"{name}: file length {len(candidate)} differs from stock length {len(stock)}"
            )
        prepared.append((name, candidate, runs))
    return _plan_merge_prepared(stock, prepared, row_size)


def _plan_merge_prepared(stock: bytes, mods: Sequence[tuple[str, bytes, list[ByteRun]]],
                         row_size: int = 0) -> tuple[bytes, list[Conflict]]:
    if row_size < 0:
        raise ValueError("row_size cannot be negative")
    output = bytearray(stock)
    # Track ownership as intervals rather than one Python object per byte. Game
    # resources can be large, and a per-byte owner array can consume many times
    # the size of the resource in RAM.
    owners: list[OwnerInterval] = []
    conflicts: list[Conflict] = []
    for name, candidate, runs in mods:
        prior_owners = owners
        row_conflicts: dict[str, set[int]] = {}
        for run in runs:
            for interval in prior_owners:
                if row_size:
                    if interval.end // row_size < run.start // row_size:
                        continue
                    if interval.start // row_size > run.end // row_size:
                        break
                    first_row = max(interval.start // row_size, run.start // row_size)
                    last_row = min(interval.end // row_size, run.end // row_size)
                    for row in range(first_row, last_row + 1):
                        start = row * row_size
                        end = min(start + row_size, len(stock))
                        # Row-aware targets intentionally report a collision if two mods
                        # changed the same record, even when their byte ranges are disjoint.
                        # Comparing slices also avoids a Python-level loop over each byte.
                        # Ownership marks bytes an earlier mod changed relative to
                        # stock. A later mod changing the same record is a collision
                        # even if it restores an earlier field to stock.
                        if candidate[start:end] != stock[start:end]:
                            row_conflicts.setdefault(interval.owner, set()).add(row)
                    continue
                if interval.end < run.start:
                    continue
                if interval.start > run.end:
                    break
                start = max(interval.start, run.start)
                end = min(interval.end, run.end) + 1
                if output[start:end] != candidate[start:end]:
                    conflicts.append(Conflict(start, end - 1, interval.owner, name))
        # Apply only after checking every run against the previous merge state.
        # This also prevents separate runs in one row from being reported as a
        # conflict between a mod and itself.
        for run in runs:
            output[run.start:run.end + 1] = candidate[run.start:run.end + 1]
            owners = _replace_owner_interval(owners, run.start, run.end, name)
        if row_size:
            for owner, rows in row_conflicts.items():
                ordered = sorted(rows)
                if not ordered:
                    continue
                first = previous = ordered[0]
                for row in ordered[1:] + [None]:
                    if row is not None and row == previous + 1:
                        previous = row
                        continue
                    start = first * row_size
                    end = min((previous + 1) * row_size, len(stock)) - 1
                    conflicts.append(Conflict(start, end, owner, name))
                    if row is not None:
                        first = previous = row
    return bytes(output), conflicts


def plan_merge_with_runs(stock: bytes, mods: Sequence[tuple[str, bytes]], row_size: int = 0) -> tuple[bytes, list[Conflict], list[ByteRun]]:
    """Merge candidates and return their changed runs for downstream processing.

    Runs are calculated once per candidate and reused by the planner and caller.
    """
    prepared: list[tuple[str, bytes, list[ByteRun]]] = []
    all_runs: list[ByteRun] = []
    for name, candidate in mods:
        runs = diff_runs(stock, candidate)
        if runs is None:
            raise MergeSafetyError(
                f"{name}: file length {len(candidate)} differs from stock length {len(stock)}"
            )
        prepared.append((name, candidate, runs))
        all_runs.extend(runs)
    merged, conflicts = _plan_merge_prepared(stock, prepared, row_size)
    return merged, conflicts, all_runs


def atomic_write(path: str | Path, data: bytes) -> None:
    """Write beside the destination and atomically replace it after a full flush."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def apply_file_transaction(changes: Sequence[tuple[str | Path, bytes]], journal: str | Path,
                           backup_root: str | Path, metadata: dict | None = None,
                           writer=atomic_write, delete_paths: Sequence[str | Path] = (),
                           preserve_backup_paths: Sequence[str | Path] = ()) -> None:
    """Stage all files, persist rollback data, then apply as one recoverable operation.

    A filesystem cannot atomically replace a set of unrelated files. The durable
    journal makes an interrupted multi-file update recoverable on the next run.
    """
    journal, backup_root = Path(journal), Path(backup_root)
    journal.parent.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    transaction_id = uuid.uuid4().hex
    staged = []
    backups = []
    deleted = []
    preserve_backups = {Path(item) for item in preserve_backup_paths}
    try:
        for index, (raw_path, payload) in enumerate(changes):
            destination = Path(raw_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            existed = destination.exists()
            backup = backup_root / f"{index:06d}.bak"
            if existed and destination not in preserve_backups:
                with destination.open("rb") as source, backup.open("xb") as target:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
            backup_name = str(backup) if existed and destination not in preserve_backups else ""
            backups.append({"path": str(destination), "backup": backup_name, "existed": existed,
                            "preserve_original": destination in preserve_backups})
            if payload is not None:
                stage = destination.with_name(f".{destination.name}.{transaction_id}.stage")
                with stage.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                staged.append((destination, stage))
            else:
                deleted.append(destination)
        record = {"id": transaction_id, "state": "applying", "files": backups,
                  "metadata": metadata or {}}
        atomic_write(journal, json.dumps(record, indent=2).encode("utf-8"))
        manifest_paths = {Path(item) for item in (metadata or {}).get("manifest_paths", [])}
        for destination, stage in staged:
            if destination not in manifest_paths:
                writer(destination, stage.read_bytes())
        for item in backups:
            destination = Path(item["path"])
            if (destination not in manifest_paths and item["existed"] and item["backup"]
                    and destination not in [d for d, _ in staged]):
                atomic_write(destination, Path(item["backup"]).read_bytes())
        for destination, stage in staged:
            if destination in manifest_paths:
                writer(destination, stage.read_bytes())
        for destination in deleted:
            destination.unlink(missing_ok=True)
        record["state"] = "committed"
        atomic_write(journal, json.dumps(record, indent=2).encode("utf-8"))
    except BaseException:
        if 'record' in locals():
            rollback_file_transaction(record, journal)
        raise
    finally:
        for _, stage in staged:
            stage.unlink(missing_ok=True)


def rollback_file_transaction(record: dict, journal: str | Path) -> None:
    """Restore a transaction's recorded pre-change files in reverse order."""
    errors = []
    for item in reversed(record.get("files", [])):
        destination = Path(item["path"])
        try:
            if item.get("preserve_original"):
                continue
            if item.get("existed"):
                atomic_write(destination, Path(item["backup"]).read_bytes())
            else:
                destination.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"{destination}: {exc}")
    if errors:
        record["state"] = "rollback_failed"
        record["rollback_errors"] = errors
        atomic_write(journal, json.dumps(record, indent=2).encode("utf-8"))
        raise OSError("transaction rollback incomplete: " + "; ".join(errors))
    if record.get("state") != "rollback_failed":
        Path(journal).unlink(missing_ok=True)


def recover_file_transaction(journal: str | Path) -> str | None:
    """Roll back a transaction left in progress by a crash or forced exit."""
    path = Path(journal)
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("state") == "committed":
        path.unlink(missing_ok=True)
        return "completed"
    rollback_file_transaction(record, path)
    return "rolled back"


def validate_sealed_input(data: bytes, label: str = "input") -> None:
    """Basic envelope validation before crypto open; sealed-box overhead is 48 bytes."""
    if not isinstance(data, bytes):
        raise TypeError(f"{label} must be bytes")
    if len(data) < 48:
        raise MergeSafetyError(f"{label} is truncated: {len(data)} bytes; minimum sealed envelope is 48")
