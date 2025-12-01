#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Dict, Any

from path_utils import get_assets_root, GARMENTS_DIR, FABRICS_DIR


def make_relative(path_str: str, root: Path) -> str:
    p = Path(path_str).expanduser()
    try:
        p = p.resolve()
    except Exception:
        # If the path can't be resolved, return original
        return path_str
    try:
        rel = p.relative_to(root)
        return str(rel)
    except ValueError:
        # Not under root; leave unchanged
        return path_str


def process_garment(data: Dict[str, Any], root: Path) -> bool:
    changed = False
    if isinstance(data.get("blend_file"), str):
        new_val = make_relative(data["blend_file"], root)
        if new_val != data["blend_file"]:
            data["blend_file"] = new_val
            changed = True
    views = data.get("views")
    if isinstance(views, list):
        for view in views:
            if not isinstance(view, dict):
                continue
            if isinstance(view.get("blend_file"), str):
                new_val = make_relative(view["blend_file"], root)
                if new_val != view["blend_file"]:
                    view["blend_file"] = new_val
                    changed = True
    return changed


def process_fabric(data: Dict[str, Any], root: Path) -> bool:
    changed = False
    materials = data.get("materials") or {}
    for _, cfg in materials.items():
        textures = cfg.get("textures") or {}
        for key, path_str in list(textures.items()):
            if isinstance(path_str, str):
                new_val = make_relative(path_str, root)
                if new_val != path_str:
                    textures[key] = new_val
                    changed = True
    return changed


def process_file(path: Path, root: Path, write: bool) -> bool:
    try:
        obj = json.loads(path.read_text())
    except Exception as e:
        print(f"❌ Skipping {path}: {e}")
        return False

    changed = False
    if path.parent == GARMENTS_DIR:
        changed = process_garment(obj, root)
    elif path.parent == FABRICS_DIR:
        changed = process_fabric(obj, root)

    if changed:
        if write:
            path.write_text(json.dumps(obj, indent=2))
            print(f"✅ Updated {path}")
        else:
            print(f"🔍 Would update {path} (run with --write to apply)")
    return changed


def main():
    write = "--write" in sys.argv
    root = get_assets_root()

    print(f"Project root: {root}")
    total = 0
    changed = 0

    for d in (GARMENTS_DIR, FABRICS_DIR):
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            total += 1
            if process_file(f, root, write):
                changed += 1

    print(f"Done. {changed}/{total} files {'updated' if write else 'would change'}.")


if __name__ == "__main__":
    main()
