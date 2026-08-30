/** Tiled JSON loader + canvas blit for LimeZu atlases. */

const FLIP_H = 0x80000000;
const FLIP_V = 0x40000000;
const FLIP_D = 0x20000000;
export const GID_MASK = ~(FLIP_H | FLIP_V | FLIP_D);

const TILESET_ROOT = "/office/tiles";

export function decodeGid(raw) {
  const value = raw >>> 0;
  return {
    gid: value & GID_MASK,
    flipH: Boolean(value & FLIP_H),
    flipV: Boolean(value & FLIP_V),
    flipD: Boolean(value & FLIP_D),
  };
}

export function resolveTileset(gid, tilesets) {
  let found = null;
  for (const ts of tilesets) {
    if (gid >= ts.firstgid && (!found || ts.firstgid > found.firstgid)) {
      const last = ts.firstgid + ts.tilecount - 1;
      if (gid <= last) found = ts;
    }
  }
  return found;
}

export function tilesetSourceRect(gid, tileset) {
  const local = gid - tileset.firstgid;
  const tw = tileset.tilewidth || 16;
  const th = tileset.tileheight || 16;
  const cols = tileset.columns || Math.floor((tileset.imagewidth || 0) / tw) || 16;
  return {
    sx: (local % cols) * tw,
    sy: Math.floor(local / cols) * th,
    tw,
    th,
  };
}

export function blitGid(ctx, tilesets, raw, dx, dy) {
  const { gid, flipH, flipV, flipD } = decodeGid(raw);
  if (!gid) return;
  const ts = resolveTileset(gid, tilesets);
  if (!ts?.img) return;
  const { sx, sy, tw, th } = tilesetSourceRect(gid, ts);
  ctx.save();
  ctx.translate(dx + tw / 2, dy + th / 2);
  if (flipD) {
    ctx.rotate(Math.PI / 2);
    ctx.scale(flipH ? 1 : -1, flipV ? -1 : 1);
  } else {
    ctx.scale(flipH ? -1 : 1, flipV ? -1 : 1);
  }
  ctx.drawImage(ts.img, sx, sy, tw, th, -tw / 2, -th / 2, tw, th);
  ctx.restore();
}

export function layerByName(map, name) {
  return (map.layers || []).find((layer) => layer.name === name) || null;
}

export function spawnTiles(map) {
  const layer = layerByName(map, "spawn-points");
  const tw = map.tilewidth || 16;
  const th = map.tileheight || 16;
  const out = {};
  for (const obj of layer?.objects || []) {
    out[obj.name] = [Math.floor(obj.x / tw), Math.floor(obj.y / th)];
  }
  return out;
}

export function collisionGrid(map) {
  const layer = layerByName(map, "collision");
  const w = map.width;
  const h = map.height;
  const grid = new Uint8Array(w * h);
  const data = layer?.data || [];
  for (let i = 0; i < data.length; i += 1) {
    grid[i] = decodeGid(data[i]).gid ? 0 : 1;
  }
  return grid;
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`tileset failed: ${src}`));
    img.src = src;
  });
}

export async function loadTiledOffice(root = TILESET_ROOT) {
  const manifestRes = await fetch(`${root}/manifest.json`);
  if (!manifestRes.ok) return null;
  const manifest = await manifestRes.json();
  const mapRes = await fetch(`${root}/${manifest.map}`);
  if (!mapRes.ok) return null;
  const map = await mapRes.json();
  const tilesets = await Promise.all(
    (manifest.tilesets || []).map(async (entry) => {
      const img = await loadImage(`${root}/${entry.image}`);
      return { ...entry, img };
    }),
  );
  return { manifest, map, tilesets };
}

export function prerenderLayers(map, tilesets, names) {
  const canvas = document.createElement("canvas");
  canvas.width = map.width * (map.tilewidth || 16);
  canvas.height = map.height * (map.tileheight || 16);
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  for (const name of names) {
    const layer = layerByName(map, name);
    if (!layer?.data || layer.visible === false) continue;
    const w = layer.width || map.width;
    const tw = map.tilewidth || 16;
    const th = map.tileheight || 16;
    layer.data.forEach((raw, i) => {
      if (!raw) return;
      const x = (i % w) * tw;
      const y = Math.floor(i / w) * th;
      blitGid(ctx, tilesets, raw, x, y);
    });
  }
  return canvas;
}

export function findMonitorTile(map, sit, offGid = 365) {
  const above = layerByName(map, "furniture-above");
  if (!above?.data) return null;
  const w = above.width || map.width;
  const candidates = [
    [sit[0], sit[1] - 2],
    [sit[0], sit[1] - 1],
    [sit[0] - 1, sit[1] - 2],
  ];
  for (const [x, y] of candidates) {
    if (x < 0 || y < 0) continue;
    const raw = above.data[y * w + x];
    if (decodeGid(raw).gid === offGid) return [x, y];
  }
  return null;
}
