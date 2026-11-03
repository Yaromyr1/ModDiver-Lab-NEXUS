"""Business actions for ModDiver Laboratory, kept out of the Tk view.

GUI split: core-adjacent logic moves here first, pages follow later.
The App keeps only layout and event wiring; these functions take (cfg, log, paths)
and do the work, so they can be tested without a display.
"""
from pathlib import Path

import core


def ensure_stock(cfg, log):
    if not core.STOCK.exists() or not any(core.STOCK.glob("*.dl_bin")):
        core.capture_stock(cfg, log)


def install_all(cfg, log, dry_run=False, progress=None):
    kwargs = {'progress': progress} if progress else {}
    if core.hellforge_root(cfg) is not None:
        return core.deploy(cfg, log, dry_run=dry_run, **kwargs)
    if dry_run:
        if not core.STOCK.exists() or not any(core.STOCK.glob('*.dl_bin')):
            raise RuntimeError('Capture clean stock before previewing deployment.')
    else:ensure_stock(cfg, log)
    return core.deploy(cfg, log, dry_run=dry_run, **kwargs)


def capture_stock(cfg, log):
    return core.capture_stock(cfg, log)


def purge(cfg, log):
    return core.purge(cfg, log)


def export_mod(cfg, path, log):
    return core.export_mod(cfg, path, log)


def add_zip(cfg, path, log):
    mod = core.parse_mod(Path(path))
    if not mod.get("targets"):
        raise RuntimeError("No deployable data in that ZIP.")
    cfg.setdefault("mods", []).append({
        "path": mod["path"], "name": mod["name"], "type": mod["type"],
        "targets": mod["targets"], "enabled": True, "selected": {},
    })
    core.save_config(cfg)
    log("added " + mod["name"])
    return mod


def set_game(cfg, path):
    cfg["game"] = str(path).strip()
    core.save_config(cfg)


def remove_mod(cfg, i, log):
    m = cfg["mods"].pop(i)
    core.save_config(cfg)
    log("removed " + str(m.get("name")) + " from the library (source files kept; use Purge to restore game files)")


def toggle_mod(cfg, i):
    m = cfg["mods"][i]
    m["enabled"] = not m.get("enabled", True)
    core.save_config(cfg)


def reorder_mod(cfg, source, target=None, after=False, category=None):
    """Move a card to any group, including an empty group header."""
    mods=cfg['mods']
    if not 0<=source<len(mods):return source
    if target is not None and not 0<=target<len(mods):return source
    category = category or (core.library_category(mods[target]) if target is not None else None)
    if category not in core.LIBRARY_CATEGORIES:return source
    if target == source and core.library_category(mods[source]) == category:return source
    if core.library_category(mods[source]) != category:
        moving = mods.pop(source)
        moving['category'] = category
        if target is None:
            slots = [i for i, mod in enumerate(mods) if core.library_category(mod) == category]
            destination = slots[-1] + 1 if slots else len(mods)
        else:
            destination = target - (source < target) + bool(after)
        mods.insert(destination, moving)
        core.save_config(cfg)
        return destination
    slots=[i for i,m in enumerate(mods) if core.library_category(m)==category]
    items=[mods[i] for i in slots];moving=items.pop(slots.index(source))
    destination=(slots.index(target)-(source<target)+bool(after)) if target is not None else len(items)
    destination=max(0,min(len(items),destination));items.insert(destination,moving)
    for slot,item in zip(slots,items):mods[slot]=item
    core.save_config(cfg)
    return slots[destination]
