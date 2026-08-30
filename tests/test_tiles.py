from __future__ import annotations

import json

from agent_mailroom.office_theme import (
    GID_MASK,
    load_manifest,
    map_gid_unresolved,
    tiles_dir,
    tileset_status,
)


def test_limezu_tilesets_are_present_and_complete():
    status = tileset_status()
    assert status["present"] is True
    assert status["engine"] == "tiled"
    assert status["missing"] == []
    assert status["credit"]["author"] == "LimeZu"
    assert "limezu.itch.io" in status["credit"]["url"]
    root = tiles_dir()
    assert (root / "LIMEZUASSETS-LICENSE.txt").is_file()
    assert (root / "ATTRIBUTION.md").is_file()
    license_text = (root / "LIMEZUASSETS-LICENSE.txt").read_text(encoding="utf-8")
    assert "LimeZu" in license_text
    assert "CREDITS ARE REQUIRED" in license_text


def test_shipped_map_gids_resolve():
    assert map_gid_unresolved() == []


def test_manifest_desks_sit_on_walkable_spawns():
    manifest = load_manifest()
    tiled = json.loads((tiles_dir() / manifest["map"]).read_text(encoding="utf-8"))
    tw, th = tiled["tilewidth"], tiled["tileheight"]
    width = tiled["width"]
    spawns = {}
    for layer in tiled["layers"]:
        if layer.get("name") == "spawn-points":
            for obj in layer.get("objects") or []:
                spawns[obj["name"]] = (int(obj["x"] // tw), int(obj["y"] // th))
        if layer.get("name") == "collision":
            collision = layer["data"]
    assert spawns
    for key, spec in manifest["desks"].items():
        assert spec["spawn"] in spawns, f"{key} missing spawn {spec['spawn']}"
        x, y = spawns[spec["spawn"]]
        gid = collision[y * width + x] & GID_MASK
        assert gid == 0, f"{key} spawn sits on a collision tile"
    assert "entrance" in spawns
    for key, spec in (manifest.get("bins") or {}).items():
        assert spec["spawn"] in spawns, f"{key} missing spawn {spec['spawn']}"
        x, y = spawns[spec["spawn"]]
        gid = collision[y * width + x] & GID_MASK
        assert gid == 0, f"{key} bin sits on a collision tile"
