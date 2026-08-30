import { collisionGrid, findMonitorTile, spawnTiles } from "./tiled.js?v=mailroom9";

export const TILE = 16;
export const SCALE = 2;

const DOORS = [
  [5, 7], [5, 8],
  [16, 6], [17, 6], [18, 6], [16, 7], [17, 7], [18, 7], [17, 8],
  [31, 7], [32, 7], [31, 8],
  [9, 12], [10, 12],
  [29, 12], [30, 12],
  [8, 16], [8, 17],
  [28, 16], [28, 17],
  [19, 21],
];

const DOOR_SET = new Set(DOORS.map(([x, y]) => `${x},${y}`));

export const PROCEDURAL_ROOMS = [
  { id: "boss", name: "BOSS", x: 1, y: 1, w: 9, h: 7, floor: "#c9a66b", trim: "#6e1423" },
  { id: "reception", name: "RECEPTION", x: 12, y: 1, w: 12, h: 6, floor: "#f0ead2", trim: "#8b6f47" },
  { id: "judge", name: "JUDGE", x: 26, y: 1, w: 13, h: 7, floor: "#e0daf2", trim: "#3d2e4a" },
  { id: "archive", name: "ARCHIVE", x: 1, y: 10, w: 9, h: 6, floor: "#d2e7da", trim: "#5ca97a" },
  { id: "report", name: "REPORT", x: 30, y: 10, w: 9, h: 6, floor: "#cfe5e9", trim: "#4f9faf" },
  { id: "bay-a", name: "BAY A", x: 1, y: 17, w: 17, h: 6, floor: "#e5c896", trim: "#8b6f47" },
  { id: "bay-b", name: "BAY B", x: 22, y: 17, w: 17, h: 6, floor: "#e5c896", trim: "#8b6f47" },
];

export const PROCEDURAL_DESKS = {
  "desk-boss": { tile: [4, 4], agent: "boss", label: "Michael", face: "down" },
  "desk-reception": { tile: [15, 3], agent: "sorter", label: "Pam", face: "down" },
  "desk-reception-2": { tile: [20, 3], agent: "sorter_reviewer", label: "Kelly", face: "down" },
  "desk-judge": { tile: [30, 3], agent: "judge", label: "Oscar", face: "down" },
  "desk-arbiter": { tile: [35, 3], agent: "arbiter", label: "Stanley", face: "down" },
  "desk-archive": { tile: [4, 12], agent: "archivist", label: "Creed", face: "right" },
  "desk-report": { tile: [34, 12], agent: "reporter", label: "Ryan", face: "left" },
  "desk-contracts": { tile: [4, 19], agent: "contracts_specialist", label: "Dwight", face: "down" },
  "desk-corporate": { tile: [12, 19], agent: "corporate_records_specialist", label: "Angela", face: "down" },
  "desk-correspondence": { tile: [25, 19], agent: "correspondence_specialist", label: "Jim", face: "down" },
  "desk-compliance": { tile: [30, 19], agent: "compliance_specialist", label: "Toby", face: "down" },
  "desk-claims": { tile: [35, 19], agent: "insurance_claims_specialist", label: "Meredith", face: "down" },
};

export const PROCEDURAL_BINS = {
  inbox: { tile: [18, 4], label: "INBOX", tab: "inbox", color: "#7d97b5", labelAnchor: "above-left", labelOffset: [0, -2] },
  classified: { tile: [21, 4], label: "SORTED", tab: "inbox", color: "#f4d35e", labelAnchor: "above-right", labelOffset: [0, -2] },
  review: { tile: [7, 4], label: "REVIEW", tab: "review", color: "#f4d35e", labelAnchor: "above", labelOffset: [0, -2] },
  archive: { tile: [6, 12], label: "ARCHIVE", tab: "archive", color: "#5ca97a", labelAnchor: "above-left", labelOffset: [0, -4] },
  failed: { tile: [3, 14], label: "RETURNS", tab: "failed", color: "#d96a62", labelAnchor: "above-right", labelOffset: [0, -4] },
};

const PROCEDURAL_WANDER = [
  [19, 14],
  [19, 22],
  [11, 13],
  [20, 9],
  [21, 19],
  [6, 14],
  [33, 14],
];

function inRoomInterior(tx, ty, rooms) {
  for (const room of rooms) {
    if (tx > room.x && tx < room.x + room.w - 1 && ty > room.y && ty < room.y + room.h - 1) {
      return true;
    }
  }
  return false;
}

function proceduralWalkable(tx, ty) {
  if (tx < 0 || ty < 0 || tx >= 40 || ty >= 24) return false;
  if (tx >= 10 && tx <= 29 && ty >= 8 && ty <= 16) return true;
  if (ty >= 21) return true;
  if (DOOR_SET.has(`${tx},${ty}`)) return true;
  return inRoomInterior(tx, ty, PROCEDURAL_ROOMS);
}

function cloneDesks(src) {
  return Object.fromEntries(
    Object.entries(src).map(([key, desk]) => [key, { ...desk, tile: [...desk.tile] }]),
  );
}

function cloneBins(src) {
  return Object.fromEntries(
    Object.entries(src).map(([key, bin]) => [key, { ...bin, tile: [...bin.tile] }]),
  );
}

export const layout = {
  source: "procedural",
  cols: 40,
  rows: 24,
  desks: cloneDesks(PROCEDURAL_DESKS),
  bins: cloneBins(PROCEDURAL_BINS),
  rooms: PROCEDURAL_ROOMS.map((r) => ({ ...r })),
  entrance: [19, 22],
  wander: PROCEDURAL_WANDER.map((t) => [...t]),
  walkGrid: null,
  credit: null,
  tiled: null,
};

export function resetLayout() {
  layout.source = "procedural";
  layout.cols = 40;
  layout.rows = 24;
  layout.desks = cloneDesks(PROCEDURAL_DESKS);
  layout.bins = cloneBins(PROCEDURAL_BINS);
  layout.rooms = PROCEDURAL_ROOMS.map((r) => ({ ...r }));
  layout.entrance = [19, 22];
  layout.wander = PROCEDURAL_WANDER.map((t) => [...t]);
  layout.walkGrid = null;
  layout.credit = null;
  layout.tiled = null;
}

export function isWalkable(tx, ty) {
  if (tx < 0 || ty < 0 || tx >= layout.cols || ty >= layout.rows) return false;
  if (layout.walkGrid) return layout.walkGrid[ty * layout.cols + tx] === 1;
  return proceduralWalkable(tx, ty);
}

export function tileToPx(tile) {
  return { x: tile[0] * TILE + TILE / 2, y: tile[1] * TILE + TILE / 2 };
}

export function applyTiledLayout({ manifest, map, tilesets, below, above }) {
  const spawns = spawnTiles(map);
  const grid = collisionGrid(map);
  const desks = {};
  for (const [key, spec] of Object.entries(manifest.desks || {})) {
    const tile = spawns[spec.spawn];
    if (!tile) continue;
    const monitor = findMonitorTile(map, tile, manifest.monitor?.offTopLeftGid || 365);
    desks[key] = {
      tile,
      agent: spec.agent,
      label: spec.label,
      face: spec.face || "down",
      spawn: spec.spawn,
      monitor,
      labelPosition: spec.labelPosition,
      labelOffset: spec.labelOffset,
    };
    grid[tile[1] * map.width + tile[0]] = 1;
  }
  const bins = {};
  for (const [key, spec] of Object.entries(manifest.bins || {})) {
    const tile = spawns[spec.spawn];
    if (!tile) continue;
    bins[key] = {
      tile,
      label: spec.label || key.toUpperCase(),
      tab: spec.tab || key,
      color: spec.color || "#f4d35e",
      spawn: spec.spawn,
      labelOffset: spec.labelOffset || [0, 0],
      labelAnchor: spec.labelAnchor || "above",
    };
    grid[tile[1] * map.width + tile[0]] = 1;
  }
  const entrance = spawns.entrance || [Math.floor(map.width / 2), map.height - 2];
  grid[entrance[1] * map.width + entrance[0]] = 1;

  const wander = (manifest.wander || [])
    .map((name) => spawns[name])
    .filter(Boolean);

  layout.source = "limezu";
  layout.cols = map.width;
  layout.rows = map.height;
  layout.desks = desks;
  layout.bins = Object.keys(bins).length ? bins : cloneBins(PROCEDURAL_BINS);
  layout.rooms = (manifest.rooms || []).map((r) => ({ ...r }));
  layout.entrance = entrance;
  layout.wander = wander.length ? wander : [entrance];
  layout.walkGrid = grid;
  layout.credit = manifest.credit || null;
  layout.tiled = {
    map,
    tilesets,
    below,
    above,
    spawns,
    monitorOn: manifest.monitor?.onGids || [[367, 0, 0], [368, 1, 0], [383, 0, 1], [384, 1, 1]],
  };
  return layout;
}

export const STAGE_DESK = {
  inbox: "desk-reception",
  ingest: "desk-reception",
  classify: "desk-reception",
  retry_classify: "desk-reception-2",
  review_classify: "desk-reception-2",
  extract: null,
  retry_extract: null,
  judge_verify: "desk-judge",
  arbiter: "desk-arbiter",
  boss: "desk-boss",
  boss_escalation: "desk-boss",
  review: "desk-boss",
  human_review: "desk-boss",
  report: "desk-report",
  compile_report: "desk-report",
  catalog: "desk-archive",
  catalog_write: "desk-archive",
  archive: "desk-archive",
  archived: "desk-archive",
};

const SPECIALIST_DESK = {
  contract: "desk-contracts",
  merger_agreement: "desk-contracts",
  corporate_record: "desk-corporate",
  correspondence: "desk-correspondence",
  compliance_filing: "desk-compliance",
  insurance_claim: "desk-claims",
};

export function deskForRun(run) {
  if (run.stage === "extract" || run.stage === "retry_extract") {
    return SPECIALIST_DESK[run.doc_type] || "desk-contracts";
  }
  return STAGE_DESK[run.stage] || "desk-reception";
}

export function binForRun(run) {
  const stage = run?.stage;
  const bin = run?.bin;
  if (stage === "inbox" || bin === "inbox") return "inbox";
  if (stage === "review" || bin === "review") return "review";
  if (stage === "archived" || stage === "archive" || bin === "archive") return "archive";
  if (stage === "failed" || bin === "failed") return "failed";
  if (stage === "classified" || bin === "classified") return "classified";
  return run?.tray || null;
}

export function getDesks() {
  return layout.desks;
}

export function getBins() {
  return layout.bins;
}
