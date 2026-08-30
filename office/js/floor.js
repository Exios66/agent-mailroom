import { CAST, ROSTER_CAST } from "./cast.js?v=mailroom7";
import {
  TILE,
  SCALE,
  layout,
  applyTiledLayout,
  deskForRun,
  binForRun,
  isWalkable,
  tileToPx,
  getDesks,
  getBins,
} from "./layout.js?v=mailroom7";
import { blitGid, loadTiledOffice, prerenderLayers } from "./tiled.js?v=mailroom7";

export { TILE, SCALE, deskForRun, binForRun, tileToPx, getDesks, getBins };

const DEFAULT_HIVE_ACTS = {
  request: "#4F9FAF",
  query: "#9482D3",
  propose: "#DCAB3C",
  inform: "#FFF8E7",
  agree: "#5CA97A",
  done: "#5CA97A",
  refuse: "#D96A62",
};
export const DESKS = new Proxy(
  {},
  {
    get(_, key) {
      if (key === Symbol.toStringTag) return "Object";
      if (key === "then") return undefined;
      const desks = getDesks();
      if (key === Symbol.iterator) return undefined;
      return desks[key];
    },
    ownKeys() {
      return Reflect.ownKeys(getDesks());
    },
    getOwnPropertyDescriptor(_, key) {
      const desks = getDesks();
      if (key in desks) return { configurable: true, enumerable: true, value: desks[key] };
      return undefined;
    },
    has(_, key) {
      return key in getDesks();
    },
  },
);

const WALK_SPEED = 48;

const QUIPS = {
  idle: ["that's what she said", "paper jam", "need coffee", "still counts", "dink-dink"],
  work: {
    classify: "sorting the pile",
    retry_classify: "re-reading it",
    review_classify: "second opinion",
    extract: "pulling the fields",
    retry_extract: "extracting again",
    judge_verify: "quality check",
    arbiter: "splitting the difference",
    boss: "that's what she said",
    boss_escalation: "escalating",
    review: "needs a human",
    human_review: "needs a human",
    report: "writing it up",
    compile_report: "writing it up",
    catalog: "cataloging",
    catalog_write: "cataloging",
    archive: "filing it away",
    archived: "filed",
    ingest: "opening the envelope",
    inbox: "new mail",
  },
};

function hexToRgb(hex) {
  const n = hex.replace("#", "");
  return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
}

function findPath(from, to) {
  const start = `${from[0]},${from[1]}`;
  const goal = `${to[0]},${to[1]}`;
  if (start === goal) return [from];
  if (!isWalkable(to[0], to[1])) return [from, to];
  const q = [[from[0], from[1]]];
  const seen = new Set([start]);
  const prev = new Map();
  const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  while (q.length) {
    const [x, y] = q.shift();
    if (`${x},${y}` === goal) break;
    for (const [dx, dy] of dirs) {
      const nx = x + dx;
      const ny = y + dy;
      const key = `${nx},${ny}`;
      if (seen.has(key) || !isWalkable(nx, ny)) continue;
      seen.add(key);
      prev.set(key, [x, y]);
      q.push([nx, ny]);
    }
  }
  if (!prev.has(goal) && start !== goal) {
    return [from, to];
  }
  const path = [to];
  let cur = goal;
  while (cur !== start) {
    const p = prev.get(cur);
    if (!p) break;
    path.push(p);
    cur = `${p[0]},${p[1]}`;
  }
  path.reverse();
  return path.length ? path : [from, to];
}

function thoughtFor(run) {
  if (!run) return "";
  if (run.conflict_detected || (run.escalation_reason || "").includes("conflict")) {
    return "matter conflict!";
  }
  if (run.needs_reconsideration) return "reconsider this filing";
  if (run.needs_human || run.stage === "review") return "needs a human";
  const verb = QUIPS.work[run.stage] || run.stage;
  const name = (run.filename || "").slice(0, 18);
  return name ? `${verb}: ${name}` : verb;
}

function drawAvatar(ctx, character, px, py, status, facing, phase) {
  const recipe = CAST[character] || CAST.pam;
  const [sr, sg, sb] = hexToRgb(recipe.skin);
  const [hr, hg, hb] = hexToRgb(recipe.hair);
  const [cr, cg, cb] = hexToRgb(recipe.shirt);
  const bob = status === "walk" ? Math.round(Math.sin(phase * 14) * 1) : 0;
  const stride = status === "walk" && Math.sin(phase * 14) > 0;
  const sit = status === "work" || status === "think";
  const x = Math.round(px - 6);
  const y = Math.round(py - 14 + bob + (sit ? 2 : 0));
  ctx.fillStyle = `rgb(${hr},${hg},${hb})`;
  if (recipe.hairStyle !== "bald") ctx.fillRect(x + 2, y, 8, 3);
  if (recipe.hairStyle === "bun") ctx.fillRect(x + 4, y - 2, 4, 2);
  if (recipe.hairStyle === "frame") ctx.fillRect(x + 1, y + 3, 2, 6);
  if (recipe.hairStyle === "floppy") ctx.fillRect(x + 1, y + 1, 3, 3);
  if (recipe.hairStyle === "spiky") {
    ctx.fillRect(x + 3, y - 2, 1, 2);
    ctx.fillRect(x + 6, y - 2, 1, 2);
  }
  ctx.fillStyle = `rgb(${sr},${sg},${sb})`;
  ctx.fillRect(x + 3, y + 3, 6, 5);
  ctx.fillStyle = `rgb(${cr},${cg},${cb})`;
  ctx.fillRect(x + 2, y + 8, 8, 6);
  ctx.fillStyle = "#1a1320";
  if (facing === "left") {
    ctx.fillRect(x + 3, y + 5, 1, 1);
    ctx.fillRect(x + 5, y + 5, 1, 1);
  } else if (facing === "right") {
    ctx.fillRect(x + 6, y + 5, 1, 1);
    ctx.fillRect(x + 8, y + 5, 1, 1);
  } else {
    ctx.fillRect(x + 4, y + 5, 1, 1);
    ctx.fillRect(x + 7, y + 5, 1, 1);
  }
  if (!sit) {
    ctx.fillRect(x + (stride ? 2 : 3), y + 14, 3, 4);
    ctx.fillRect(x + (stride ? 7 : 6), y + 14, 3, 4);
  } else {
    ctx.fillRect(x + 3, y + 14, 3, 2);
    ctx.fillRect(x + 6, y + 14, 3, 2);
  }
}

function drawBubble(ctx, px, py, text, lift) {
  if (!text) return;
  const label = text.length > 22 ? `${text.slice(0, 21)}…` : text;
  ctx.font = "6px monospace";
  const w = Math.max(32, label.length * 3.4 + 8);
  const h = 11;
  const x = Math.round(Math.max(2, Math.min(layout.cols * TILE - w - 2, px - w / 2)));
  const y = Math.round(Math.max(2, py - 24 - lift));
  ctx.fillStyle = "#1a1320";
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#fffdf5";
  ctx.fillRect(x + 1, y + 1, w - 2, h - 2);
  ctx.fillStyle = "#1a1320";
  ctx.fillRect(Math.round(px - 1), y + h, 2, 2);
  ctx.fillRect(Math.round(px), y + h + 2, 1, 1);
  ctx.fillStyle = "#3d2e4a";
  ctx.fillText(label, x + 3, y + 7);
}

function drawFurniture(ctx) {
  const cooler = tileToPx([11, 13]);
  ctx.fillStyle = "#4f9faf";
  ctx.fillRect(cooler.x - 5, cooler.y - 10, 10, 16);
  ctx.fillStyle = "#cfe5e9";
  ctx.fillRect(cooler.x - 4, cooler.y - 14, 8, 6);
  ctx.fillStyle = "#fff8e7";
  ctx.fillRect(cooler.x - 2, cooler.y + 2, 4, 3);

  const plantA = tileToPx([8, 9]);
  const plantB = tileToPx([22, 15]);
  for (const p of [plantA, plantB]) {
    ctx.fillStyle = "#8b6f47";
    ctx.fillRect(p.x - 3, p.y + 2, 6, 4);
    ctx.fillStyle = "#5ca97a";
    ctx.fillRect(p.x - 4, p.y - 6, 8, 8);
  }

  const coffee = tileToPx([21, 10]);
  ctx.fillStyle = "#6e1423";
  ctx.fillRect(coffee.x - 6, coffee.y - 4, 12, 8);
  ctx.fillStyle = "#f4d35e";
  ctx.fillRect(coffee.x - 4, coffee.y - 2, 3, 3);

  const shelves = tileToPx([3, 11]);
  ctx.fillStyle = "#8b6f47";
  ctx.fillRect(shelves.x - 10, shelves.y - 8, 20, 18);
  ctx.fillStyle = "#c9a66b";
  ctx.fillRect(shelves.x - 9, shelves.y - 6, 18, 3);
  ctx.fillRect(shelves.x - 9, shelves.y, 18, 3);
  ctx.fillRect(shelves.x - 9, shelves.y + 6, 18, 3);

  const window = tileToPx([4, 2]);
  ctx.fillStyle = "#cfe5e9";
  ctx.fillRect(window.x - 10, window.y - 6, 20, 10);
  ctx.strokeStyle = "#6e1423";
  ctx.strokeRect(window.x - 10, window.y - 6, 20, 10);
  ctx.fillStyle = "#f4d35e";
  ctx.fillRect(window.x - 8, window.y - 10, 16, 3);

  const hopper = tileToPx([18, 4]);
  ctx.fillStyle = "#6e1423";
  ctx.fillRect(hopper.x - 8, hopper.y + 4, 16, 6);
  ctx.fillStyle = "#7d97b5";
  ctx.fillRect(hopper.x - 6, hopper.y - 2, 12, 8);
  ctx.fillStyle = "#fff8e7";
  ctx.font = "4px monospace";
  ctx.fillText("INBOX", hopper.x - 8, hopper.y + 3);
}

function drawMiniEnvelope(ctx, x, y, stamp) {
  ctx.fillStyle = "#1a1320";
  ctx.fillRect(x - 5, y - 4, 10, 8);
  ctx.fillStyle = "#fff8e7";
  ctx.fillRect(x - 4, y - 3, 8, 6);
  ctx.fillStyle = stamp || "#a09f9f";
  ctx.fillRect(x - 4, y - 3, 8, 2);
}

function drawTray(ctx, bin, pile, hover) {
  const p = tileToPx(bin.tile);
  ctx.fillStyle = "#6b5340";
  ctx.fillRect(p.x - 11, p.y - 2, 22, 11);
  ctx.fillStyle = hover ? "#fff8e7" : bin.color || "#c9a66b";
  ctx.fillRect(p.x - 11, p.y - 5, 22, 4);
  ctx.fillStyle = "#1a1320";
  ctx.fillRect(p.x - 11, p.y - 5, 22, 1);
  const stack = (pile || []).slice(0, 6);
  stack.forEach((run, i) => {
    const ox = (i % 3) * 5 - 5;
    const oy = -7 - Math.floor(i / 3) * 4;
    drawMiniEnvelope(ctx, p.x + ox, p.y + oy, run.stamp);
  });
  ctx.fillStyle = "#fff8e7";
  ctx.font = "4px monospace";
  ctx.fillText(bin.label || "BIN", p.x - 10, p.y + 13);
  if (pile?.length) {
    ctx.fillStyle = "#1a1320";
    ctx.fillRect(p.x + 6, p.y - 12, 8, 7);
    ctx.fillStyle = "#f4d35e";
    ctx.font = "5px monospace";
    ctx.fillText(String(pile.length), p.x + 7, p.y - 7);
  }
}

function drawDeskSet(ctx, desk, working) {
  const p = tileToPx(desk.tile);
  ctx.fillStyle = "#6b5340";
  ctx.fillRect(p.x - 4, p.y + 4, 6, 5);
  ctx.fillStyle = "#8b6f47";
  ctx.fillRect(p.x - 8, p.y - 4, 16, 10);
  ctx.fillStyle = "#f4e9c7";
  ctx.fillRect(p.x - 7, p.y - 3, 14, 4);
  ctx.fillStyle = working ? "#f4d35e" : "#3d2e4a";
  ctx.fillRect(p.x + 2, p.y - 8, 7, 6);
  if (working) {
    ctx.fillStyle = "#4f9faf";
    ctx.fillRect(p.x + 3, p.y - 7, 5, 3);
  }
  ctx.fillStyle = "#fff8e7";
  ctx.fillRect(p.x - 6, p.y - 2, 3, 2);
}

function drawRoomPlates(ctx) {
  ctx.font = "5px monospace";
  for (const room of layout.rooms) {
    const x = room.x * TILE + 3;
    const y = room.y * TILE + 7;
    const w = Math.max(28, room.name.length * 3.3 + 6);
    ctx.fillStyle = "rgba(26,19,32,0.72)";
    ctx.fillRect(x - 1, y - 5, w, 8);
    ctx.fillStyle = "#fff8e7";
    ctx.fillText(room.name, x, y);
  }
}

function drawProceduralGround(ctx) {
  ctx.fillStyle = "#7aa35a";
  ctx.fillRect(0, 0, layout.cols * TILE, layout.rows * TILE);
  for (let y = 0; y < layout.rows; y += 1) {
    for (let x = 0; x < layout.cols; x += 1) {
      const path = (x >= 10 && x <= 29 && y >= 8 && y <= 16) || y >= 21;
      ctx.fillStyle = path ? ((x + y) % 2 ? "#e8d8b0" : "#dccfa4") : ((x + y) % 2 ? "#b5d589" : "#9fc86e");
      ctx.fillRect(x * TILE, y * TILE, TILE, TILE);
    }
  }
  for (const room of layout.rooms) {
    ctx.fillStyle = room.floor || "#e5c896";
    ctx.fillRect(room.x * TILE, room.y * TILE, room.w * TILE, room.h * TILE);
    ctx.strokeStyle = room.trim || "#8b6f47";
    ctx.lineWidth = 2;
    ctx.strokeRect(room.x * TILE + 1, room.y * TILE + 1, room.w * TILE - 2, room.h * TILE - 2);
    ctx.fillStyle = room.trim || "#8b6f47";
    ctx.fillRect(room.x * TILE, room.y * TILE, room.w * TILE, 8);
    ctx.fillStyle = "#fff8e7";
    ctx.font = "5px monospace";
    ctx.fillText(room.name, room.x * TILE + 3, room.y * TILE + 6);
  }
}

class Avatar {
  constructor(deskKey) {
    const desk = getDesks()[deskKey];
    const p = tileToPx(desk.tile);
    this.deskKey = deskKey;
    this.agent = desk.agent;
    this.label = desk.label;
    this.character = ROSTER_CAST[desk.agent];
    this.x = p.x;
    this.y = p.y - 2;
    this.path = [];
    this.status = "idle";
    this.thought = "";
    this.facing = desk.face || "down";
    this.phase = Math.random() * 10;
    this.idleIn = 2 + Math.random() * 6;
    this.linger = 0;
    this.work = null;
    this.home = [desk.tile[0], desk.tile[1]];
  }

  tile() {
    return [Math.round((this.x - TILE / 2) / TILE), Math.round((this.y - TILE / 2) / TILE)];
  }

  walkTo(tile) {
    this.path = findPath(this.tile(), tile).slice(1);
    if (this.path.length) this.status = "walk";
  }

  assignWork(run) {
    const same = this.work && this.work.doc_id === run.doc_id && this.work.stage === run.stage;
    this.work = run;
    this.thought = thoughtFor(run);
    if (!same) this.walkTo(this.home);
  }

  clearWork() {
    this.work = null;
    this.thought = "";
    this.idleIn = 1 + Math.random() * 4;
  }

  step(dt) {
    this.phase += dt;
    if (this.path.length) {
      const dest = tileToPx(this.path[0]);
      const tx = dest.x;
      const ty = dest.y - 2;
      const dx = tx - this.x;
      const dy = ty - this.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 1.2) {
        this.x = tx;
        this.y = ty;
        this.path.shift();
        if (!this.path.length) {
          this.status = this.work ? "work" : "idle";
          if (!this.work) this.facing = getDesks()[this.deskKey].face || "down";
        }
        return;
      }
      this.status = "walk";
      this.facing = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
      const step = WALK_SPEED * dt;
      this.x += (dx / dist) * Math.min(step, dist);
      this.y += (dy / dist) * Math.min(step, dist);
      return;
    }
    if (this.work) {
      this.status = this.work.needs_human ? "think" : "work";
      this.thought = thoughtFor(this.work);
      this.facing = getDesks()[this.deskKey].face || "down";
      return;
    }
    this.idleIn -= dt;
    if (this.linger > 0) {
      this.linger -= dt;
      this.status = "idle";
      if (this.linger <= 0) this.walkTo(this.home);
      return;
    }
    if (this.idleIn <= 0) {
      const spots = layout.wander;
      const spot = spots[Math.floor(Math.random() * spots.length)];
      this.walkTo(spot);
      this.thought = QUIPS.idle[Math.floor(Math.random() * QUIPS.idle.length)];
      this.linger = 1.6 + Math.random() * 2.2;
      this.idleIn = 6 + Math.random() * 8;
    } else if (this.status === "idle" && this.phase % 8 < 0.05) {
      this.thought = "";
    }
  }
}

export class OfficeFloor {
  constructor(canvas, onSelect) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onSelect = onSelect;
    this.runs = new Map();
    this.envelopes = [];
    this.piles = {};
    this.hiveActs = { ...DEFAULT_HIVE_ACTS };
    this.avatars = {};
    this.lastDesk = {};
    this.t = 0;
    this.hover = null;
    this.themeSource = "procedural";
    this.ready = false;
    this._pendingSnapshot = null;
    this.replayTimers = [];
    this.errandSpot = [21, 10];
    this.booted = Promise.resolve();
    canvas.addEventListener("click", (ev) => this._click(ev));
    canvas.addEventListener("mousemove", (ev) => this._hover(ev));
    this.booted = this._boot();
    requestAnimationFrame((now) => this._tick(now));
  }

  async _boot() {
    try {
      const packed = await loadTiledOffice();
      if (packed) {
        const below = prerenderLayers(packed.map, packed.tilesets, ["floor", "walls", "furniture-below"]);
        const above = prerenderLayers(packed.map, packed.tilesets, ["furniture-above"]);
        applyTiledLayout({ ...packed, below, above });
      }
    } catch (err) {
      console.warn("LimeZu tileset unavailable; using procedural floor", err);
    }
    this.themeSource = layout.source;
    this._rebuildAvatars();
    this._resize();
    this.ready = true;
    if (this._pendingSnapshot) {
      const queued = this._pendingSnapshot;
      this._pendingSnapshot = null;
      if (Array.isArray(queued)) this.applySnapshot(queued);
      else this.applySnapshot(queued.runs || [], queued.binIndex);
    }
    this._announceTheme();
  }

  _announceTheme() {
    const legend = document.querySelector("[data-testid='floor-legend']");
    if (legend && layout.source === "limezu") {
      legend.textContent = "LimeZu interiors · click a tray, avatar, envelope, or desk · gold thought = live work";
    }
    const credit = document.getElementById("limezu-credit");
    if (credit) {
      credit.hidden = layout.source !== "limezu";
    }
    window.__MAILROOM__ = {
      theme: layout.source,
      desktop: Boolean(window.mailroomDesktop?.isDesktop),
      desks: Object.keys(getDesks()),
      bins: Object.keys(getBins()),
      cols: layout.cols,
      rows: layout.rows,
    };
  }

  _rebuildAvatars() {
    this.avatars = {};
    for (const key of Object.keys(getDesks())) {
      this.avatars[getDesks()[key].agent] = new Avatar(key);
    }
  }

  _resize() {
    this.canvas.width = layout.cols * TILE * SCALE;
    this.canvas.height = layout.rows * TILE * SCALE;
    this.canvas.dataset.theme = layout.source;
  }

  setHiveActs(acts) {
    this.hiveActs = { ...DEFAULT_HIVE_ACTS, ...(acts || {}) };
  }

  applySnapshot(runs, binIndex) {
    if (!this.ready) {
      this._pendingSnapshot = { runs, binIndex };
      return;
    }
    const seen = new Set();
    const busy = {};
    const desks = getDesks();
    const piles = { inbox: [], classified: [], review: [], archive: [], failed: [] };
    for (const run of runs) {
      seen.add(run.doc_id);
      const prev = this.runs.get(run.doc_id);
      const desk = deskForRun(run);
      const tray = binForRun(run);
      if (prev && prev.desk && prev.desk !== desk) {
        this._fly(prev.desk, desk, run);
      } else if (!prev) {
        this._fly(null, desk, run);
      }
      this.runs.set(run.doc_id, { ...run, desk, tray });
      this.lastDesk[run.doc_id] = desk;
      if (tray && piles[tray]) piles[tray].push(this.runs.get(run.doc_id));
      const active = run.stage !== "archived" && run.stage !== "failed" && run.stage !== "inbox" && run.stage !== "review";
      if (active) {
        const agent = desks[desk]?.agent;
        if (agent) busy[agent] = run;
      }
    }
    if (binIndex) {
      for (const [key, payload] of Object.entries(binIndex)) {
        if (!piles[key]) piles[key] = [];
        const have = new Set(piles[key].map((row) => row.doc_id));
        for (const row of payload.documents || []) {
          if (!have.has(row.doc_id)) piles[key].push(row);
        }
      }
    }
    this.piles = piles;
    for (const id of [...this.runs.keys()]) {
      if (!seen.has(id)) {
        const gone = this.runs.get(id);
        if (gone && gone.stage !== "archived" && gone.stage !== "failed") this.runs.delete(id);
      }
    }
    for (const avatar of Object.values(this.avatars)) {
      const run = busy[avatar.agent];
      if (run) avatar.assignWork(run);
      else if (avatar.work) avatar.clearWork();
    }
  }

  ingestEvent(event) {
    if (event.type === "pipeline" && event.doc_id) {
      const run = {
        doc_id: event.doc_id,
        filename: event.filename,
        stage: event.stage,
        doc_type: event.doc_type,
        stamp: event.stamp,
        classification_confidence: event.classification_confidence,
        extraction_confidence: event.extraction_confidence,
        needs_human: event.needs_human,
        routing_path: event.routing_path,
        extracted_data: event.extracted_data,
        report: event.report,
        escalation_reason: event.escalation_reason,
        conflict_detected: event.conflict_detected,
      };
      this.applySnapshot([run, ...[...this.runs.values()].filter((r) => r.doc_id !== run.doc_id)]);
    }
    if (event.type === "hive") {
      const desks = Object.values(getDesks());
      const fromDesk = desks.find((d) => d.agent === event.from);
      const toDesk = desks.find((d) => d.agent === event.to);
      if (toDesk) {
        this.envelopes.push({
          from: fromDesk ? fromDesk.tile : layout.entrance,
          to: toDesk.tile,
          t: 0,
          dur: 0.9,
          stamp: this.hiveActs[event.act] || (event.needs_human ? "#d96a62" : "#f4d35e"),
          act: event.act,
          label: event.subject,
          doc_id: event.doc_id,
        });
        const dest = this.avatars[event.to];
        if (dest && !dest.work) {
          dest.thought = event.subject || event.act || "mail";
          dest.walkTo(toDesk.tile);
        }
      }
    }
  }

  _fly(fromKey, toKey, run) {
    const desks = getDesks();
    const bins = getBins();
    const tray = binForRun(run);
    const from = fromKey ? desks[fromKey]?.tile : layout.entrance;
    const to = (tray && bins[tray]?.tile) || desks[toKey]?.tile || layout.entrance;
    this.envelopes.push({
      from,
      to,
      t: 0,
      dur: 1.0,
      stamp: run.stamp || "#a09f9f",
      act: "inform",
      label: run.filename,
      doc_id: run.doc_id,
    });
    if (this.envelopes.length > 24) this.envelopes.shift();
  }

  _tick(now) {
    const dt = this._last ? Math.min(0.05, (now - this._last) / 1000) : 0.016;
    this._last = now;
    this.t += dt;
    for (const env of this.envelopes) env.t += dt / env.dur;
    this.envelopes = this.envelopes.filter((e) => e.t < 1.15);
    for (const avatar of Object.values(this.avatars)) avatar.step(dt);
    if (Math.random() < dt * 0.02) this._spawnErrand();
    this.draw();
    requestAnimationFrame((n) => this._tick(n));
  }

  _drawMonitors(ctx) {
    const tiled = layout.tiled;
    if (!tiled) return;
    for (const desk of Object.values(getDesks())) {
      const working = Boolean(this.avatars[desk.agent]?.work);
      if (!working || !desk.monitor) continue;
      for (const [gid, dx, dy] of tiled.monitorOn) {
        blitGid(ctx, tiled.tilesets, gid, (desk.monitor[0] + dx) * TILE, (desk.monitor[1] + dy) * TILE);
      }
    }
  }

  draw() {
    const ctx = this.ctx;
    ctx.imageSmoothingEnabled = false;
    ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
    ctx.clearRect(0, 0, layout.cols * TILE, layout.rows * TILE);

    if (layout.tiled?.below) {
      ctx.drawImage(layout.tiled.below, 0, 0);
    } else {
      drawProceduralGround(ctx);
      drawFurniture(ctx);
      const door = tileToPx(layout.entrance);
      ctx.fillStyle = "#6e1423";
      ctx.fillRect(door.x - 10, door.y - 6, 20, 12);
      ctx.fillStyle = "#f4d35e";
      ctx.fillRect(door.x - 8, door.y - 4, 16, 8);
    }

    if (layout.source === "limezu") drawRoomPlates(ctx);

    for (const [key, bin] of Object.entries(getBins())) {
      drawTray(ctx, bin, this.piles[key] || [], this.hover === `bin:${key}`);
    }

    for (const [key, desk] of Object.entries(getDesks())) {
      const working = Boolean(this.avatars[desk.agent]?.work);
      if (layout.source !== "limezu") drawDeskSet(ctx, desk, working);
      if (this.hover === key || working) {
        const p = tileToPx(desk.tile);
        ctx.strokeStyle = working ? "#f4d35e" : "#fff8e7";
        ctx.lineWidth = 1;
        ctx.strokeRect(p.x - 10, p.y - 18, 20, 26);
      }
    }

    const people = Object.values(this.avatars).sort((a, b) => a.y - b.y);

    for (const env of this.envelopes) {
      const t = Math.min(1, env.t);
      const ease = t * t * (3 - 2 * t);
      const x0 = env.from[0] * TILE + 8;
      const y0 = env.from[1] * TILE + 8;
      const x1 = env.to[0] * TILE + 8;
      const y1 = env.to[1] * TILE + 8;
      const x = x0 + (x1 - x0) * ease;
      const y = y0 + (y1 - y0) * ease - Math.sin(Math.PI * t) * 18;
      ctx.fillStyle = "#1a1320";
      ctx.fillRect(x - 8, y - 6, 16, 12);
      ctx.fillStyle = "#fff8e7";
      ctx.fillRect(x - 7, y - 5, 14, 10);
      ctx.fillStyle = env.stamp || "#a09f9f";
      ctx.fillRect(x - 7, y - 5, 14, 3);
      ctx.strokeStyle = "#1a1320";
      ctx.beginPath();
      ctx.moveTo(x - 7, y - 2);
      ctx.lineTo(x, y + 2);
      ctx.lineTo(x + 7, y - 2);
      ctx.stroke();
    }

    if (layout.tiled?.above) {
      ctx.drawImage(layout.tiled.above, 0, 0);
      this._drawMonitors(ctx);
    }

    // Avatars after furniture-above so desk tops don't bury the cast.
    for (const avatar of people) {
      drawAvatar(ctx, avatar.character, avatar.x, avatar.y, avatar.status, avatar.facing, avatar.phase);
    }

    let lift = 0;
    const bubbles = people.filter((a) => a.thought && (a.status === "work" || a.status === "think" || a.status === "walk"));
    bubbles.sort((a, b) => a.x - b.x);
    for (const avatar of bubbles) {
      const overlap = bubbles.some((other) => other !== avatar && Math.abs(other.x - avatar.x) < 28 && Math.abs(other.y - avatar.y) < 16);
      drawBubble(ctx, avatar.x, avatar.y, avatar.thought, overlap ? lift : 0);
      if (overlap) lift += 10;
    }
  }

  _pos(ev) {
    const rect = this.canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * layout.cols * TILE;
    const y = ((ev.clientY - rect.top) / rect.height) * layout.rows * TILE;
    return { x, y };
  }

  _hitDesk(x, y) {
    for (const [key, desk] of Object.entries(getDesks())) {
      const p = tileToPx(desk.tile);
      if (Math.abs(x - p.x) < 12 && Math.abs(y - p.y) < 16) return key;
    }
    return null;
  }

  _hitBin(x, y) {
    for (const [key, bin] of Object.entries(getBins())) {
      const p = tileToPx(bin.tile);
      if (Math.abs(x - p.x) < 14 && Math.abs(y - p.y) < 16) return key;
    }
    return null;
  }

  _hitAvatar(x, y) {
    for (const avatar of Object.values(this.avatars)) {
      if (Math.abs(x - avatar.x) < 8 && Math.abs(y - avatar.y) < 14) return avatar;
    }
    return null;
  }

  _hitEnvelope(x, y) {
    for (const env of this.envelopes) {
      const t = Math.min(1, env.t);
      const ease = t * t * (3 - 2 * t);
      const px = env.from[0] * TILE + 8 + (env.to[0] * TILE + 8 - (env.from[0] * TILE + 8)) * ease;
      const py = env.from[1] * TILE + 8 + (env.to[1] * TILE + 8 - (env.from[1] * TILE + 8)) * ease;
      if (Math.abs(x - px) < 10 && Math.abs(y - py) < 10) return env;
    }
    return null;
  }

  _hover(ev) {
    const { x, y } = this._pos(ev);
    const bin = this._hitBin(x, y);
    this.hover = bin ? `bin:${bin}` : this._hitDesk(x, y);
  }

  _click(ev) {
    const { x, y } = this._pos(ev);
    const env = this._hitEnvelope(x, y);
    if (env && env.doc_id) {
      this.onSelect(this.runs.get(env.doc_id) || { doc_id: env.doc_id, filename: env.label });
      return;
    }
    const trayKey = this._hitBin(x, y);
    if (trayKey) {
      const bin = getBins()[trayKey];
      const pile = this.piles[trayKey] || [];
      this.onSelect({
        tray: trayKey,
        tab: bin?.tab || trayKey,
        filename: `${bin?.label || trayKey} tray`,
        thought: pile.length ? `${pile.length} filing${pile.length === 1 ? "" : "s"} in the ${trayKey} bin` : `empty ${trayKey} bin`,
        documents: pile,
        stage: trayKey,
        bin: trayKey,
      });
      return;
    }
    const person = this._hitAvatar(x, y);
    if (person) {
      this.onSelect(person.work || { desk: person.deskKey, agent: person.agent, filename: person.label, thought: person.thought });
      return;
    }
    const deskKey = this._hitDesk(x, y);
    if (!deskKey) return;
    const desk = getDesks()[deskKey];
    const run = [...this.runs.values()].find((r) => r.desk === deskKey && !r.tray);
    this.onSelect(run || { desk: deskKey, agent: desk.agent, filename: desk.label });
  }

  clearReplayTimers() {
    for (const timer of this.replayTimers) clearTimeout(timer);
    this.replayTimers = [];
  }

  replay(runData) {
    this.clearReplayTimers();
    const replayId = runData.trace_id || runData.doc_id;
    if (!replayId) return;
    const spanToStage = {
      "ingest-document": "ingest",
      "classify-document": "classify",
      "extract-fields": "extract",
      "judge-verify": "judge_verify",
      "arbitrate-verdict": "arbiter",
      "compile-report": "report",
      "archive-document": "archived",
    };
    let sequence = (runData.routing_path || []).slice();
    const spans = runData.spans || [];
    if (spans.length) {
      sequence = spans
        .map((span) => spanToStage[span.name] || span.name)
        .filter(Boolean);
    }
    if (!sequence.length) sequence = ["ingest", "classify", "extract", "archive", "archived"];
    const baseRun = {
      doc_id: replayId,
      trace_id: replayId,
      filename: runData.filename,
      doc_type: runData.doc_type,
      stage: sequence[0],
      routing_path: sequence,
    };
    this.runs.set(replayId, { ...baseRun, desk: deskForRun(baseRun) });
    let delay = 0;
    for (const stage of sequence) {
      const timer = setTimeout(() => {
        const current = this.runs.get(replayId);
        if (!current) return;
        current.stage = stage;
        current.desk = deskForRun(current);
        this.runs.set(replayId, current);
      }, delay);
      this.replayTimers.push(timer);
      const span = spans.find((row) => (spanToStage[row.name] || row.name) === stage);
      delay += Math.min(1800, Math.max(350, Number(span?.latency_ms || 600)));
    }
    const endTimer = setTimeout(() => {
      const current = this.runs.get(replayId);
      if (current) {
        current.stage = runData.stage || "archived";
        this.runs.set(replayId, current);
      }
    }, delay + 400);
    this.replayTimers.push(endTimer);
  }

  _spawnErrand() {
    const idle = Object.values(this.avatars).filter((a) => !a.work && a.status === "idle");
    if (!idle.length) return;
    const avatar = idle[Math.floor(Math.random() * idle.length)];
    avatar.thought = Math.random() > 0.5 ? "coffee run" : "errand";
    avatar.walkTo(this.errandSpot);
    avatar.linger = 2.2;
  }
}
