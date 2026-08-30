from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GID_MASK = 0x1FFFFFFF


def office_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "office",
        Path.cwd() / "office",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def tiles_dir() -> Path:
    return office_dir() / "tiles"


def load_manifest() -> dict[str, Any]:
    path = tiles_dir() / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def tileset_status() -> dict[str, Any]:
    root = tiles_dir()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"present": False, "engine": None, "missing": ["manifest.json"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing: list[str] = []
    map_rel = manifest.get("map", "maps/office.tmj")
    if not (root / map_rel).is_file():
        missing.append(map_rel)
    images = []
    for entry in manifest.get("tilesets", []):
        rel = entry.get("image", "")
        images.append(rel)
        if rel and not (root / rel).is_file():
            missing.append(rel)
    license_path = root / "LIMEZUASSETS-LICENSE.txt"
    if not license_path.is_file():
        missing.append("LIMEZUASSETS-LICENSE.txt")
    credit = manifest.get("credit") or {}
    return {
        "present": not missing,
        "engine": manifest.get("engine", "tiled"),
        "id": manifest.get("id"),
        "map": map_rel,
        "tilesets": images,
        "missing": missing,
        "credit": credit,
        "fallback": "procedural",
    }


def map_gid_unresolved(limit: int = 20) -> list[dict[str, Any]]:
    """Return GIDs on the shipped map that do not resolve to a manifest tileset."""
    manifest = load_manifest()
    root = tiles_dir()
    tiled = json.loads((root / manifest["map"]).read_text(encoding="utf-8"))
    ranges = []
    for entry in manifest.get("tilesets", []):
        first = int(entry["firstgid"])
        count = int(entry["tilecount"])
        ranges.append((first, first + count - 1, entry["name"]))
    bad: list[dict[str, Any]] = []
    for layer in tiled.get("layers", []):
        if layer.get("type") != "tilelayer":
            continue
        for raw in layer.get("data") or []:
            gid = int(raw) & GID_MASK
            if not gid:
                continue
            if not any(lo <= gid <= hi for lo, hi, _ in ranges):
                bad.append({"layer": layer.get("name"), "gid": gid})
                if len(bad) >= limit:
                    return bad
    return bad
