import { CAST, ROSTER_CAST } from "./cast.js";

export const TILE = 16;
export const COLS = 40;
export const ROWS = 24;
export const SCALE = 2;
const WALK_SPEED = 48;

export const ROOMS = [
  { id: "boss", name: "BOSS", x: 1, y: 1, w: 9, h: 7, floor: "#c9a66b", trim: "#6e1423" },
  { id: "reception", name: "RECEPTION", x: 12, y: 1, w: 12, h: 6, floor: "#f0ead2", trim: "#8b6f47" },
  { id: "judge", name: "JUDGE", x: 26, y: 1, w: 13, h: 7, floor: "#e0daf2", trim: "#3d2e4a" },
  { id: "archive", name: "ARCHIVE", x: 1, y: 10, w: 9, h: 6, floor: "#d2e7da", trim: "#5ca97a" },
  { id: "report", name: "REPORT", x: 30, y: 10, w: 9, h: 6, floor: "#cfe5e9", trim: "#4f9faf" },
  { id: "bay-a", name: "BAY A", x: 1, y: 17, w: 17, h: 6, floor: "#e5c896", trim: "#8b6f47" },
  { id: "bay-b", name: "BAY B", x: 22, y: 17, w: 17, h: 6, floor: "#e5c896", trim: "#8b6f47" },
];

export const DESKS = {
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

export const ENTRANCE = [19, 22];

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

const WANDER = [
  [19, 14],
  [19, 22],
  [11, 13],
  [20, 9],
  [21, 19],
  [6, 14],
  [33, 14],
];

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

export function tileToPx(tile) {
  return { x: tile[0] * TILE + TILE / 2, y: tile[1] * TILE + TILE / 2 };
}

function hexToRgb(hex) {
  const n = hex.replace("#", "");
  return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
}

function doorKey(x, y) {
  return `${x},${y}`;
}

const DOOR_SET = new Set(DOORS.map(([x, y]) => doorKey(x, y)));

function inRoomInterior(tx, ty) {
  for (const room of ROOMS) {
    if (tx > room.x && tx < room.x + room.w - 1 && ty > room.y && ty < room.y + room.h - 1) {
      return true;
    }
  }
  return false;
}

function isWalkable(tx, ty) {
  if (tx < 0 || ty < 0 || tx >= COLS || ty >= ROWS) return false;
  if (tx >= 10 && tx <= 29 && ty >= 8 && ty <= 16) return true;
  if (ty >= 21) return true;
  if (DOOR_SET.has(doorKey(tx, ty))) return true;
  return inRoomInterior(tx, ty);
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
  ctx.font = "5px monospace";
  const w = Math.max(28, label.length * 3 + 6);
  const h = 9;
  const x = Math.round(Math.max(2, Math.min(COLS * TILE - w - 2, px - w / 2)));
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

class Avatar {
  constructor(deskKey) {
    const desk = DESKS[deskKey];
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
    if (this.path.length) this.status = this.work ? "walk" : "walk";
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
          if (!this.work) this.facing = DESKS[this.deskKey].face || "down";
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
      this.facing = DESKS[this.deskKey].face || "down";
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
      const spot = WANDER[Math.floor(Math.random() * WANDER.length)];
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
    this.avatars = {};
    for (const key of Object.keys(DESKS)) {
      this.avatars[DESKS[key].agent] = new Avatar(key);
    }
    this.lastDesk = {};
    this.t = 0;
    this.hover = null;
    canvas.addEventListener("click", (ev) => this._click(ev));
    canvas.addEventListener("mousemove", (ev) => this._hover(ev));
    requestAnimationFrame((now) => this._tick(now));
  }

  applySnapshot(runs) {
    const seen = new Set();
    const busy = {};
    for (const run of runs) {
      seen.add(run.doc_id);
      const prev = this.runs.get(run.doc_id);
      const desk = deskForRun(run);
      if (prev && prev.desk && prev.desk !== desk) {
        this._fly(prev.desk, desk, run);
      } else if (!prev) {
        this._fly(null, desk, run);
      }
      this.runs.set(run.doc_id, { ...run, desk });
      this.lastDesk[run.doc_id] = desk;
      const active = run.stage !== "archived" && run.stage !== "failed";
      if (active) {
        const agent = DESKS[desk]?.agent;
        if (agent) busy[agent] = run;
      }
    }
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
      const fromDesk = Object.values(DESKS).find((d) => d.agent === event.from);
      const toDesk = Object.values(DESKS).find((d) => d.agent === event.to);
      if (toDesk) {
        this.envelopes.push({
          from: fromDesk ? fromDesk.tile : ENTRANCE,
          to: toDesk.tile,
          t: 0,
          dur: 0.9,
          stamp: event.needs_human ? "#d96a62" : "#f4d35e",
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
    const from = fromKey ? DESKS[fromKey]?.tile : ENTRANCE;
    const to = DESKS[toKey]?.tile || ENTRANCE;
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
    this.draw();
    requestAnimationFrame((n) => this._tick(n));
  }

  draw() {
    const ctx = this.ctx;
    ctx.imageSmoothingEnabled = false;
    ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
    ctx.fillStyle = "#7aa35a";
    ctx.fillRect(0, 0, COLS * TILE, ROWS * TILE);

    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const path = (x >= 10 && x <= 29 && y >= 8 && y <= 16) || y >= 21;
        ctx.fillStyle = path ? ((x + y) % 2 ? "#e8d8b0" : "#dccfa4") : ((x + y) % 2 ? "#b5d589" : "#9fc86e");
        ctx.fillRect(x * TILE, y * TILE, TILE, TILE);
      }
    }

    for (const room of ROOMS) {
      ctx.fillStyle = room.floor;
      ctx.fillRect(room.x * TILE, room.y * TILE, room.w * TILE, room.h * TILE);
      ctx.strokeStyle = room.trim;
      ctx.lineWidth = 2;
      ctx.strokeRect(room.x * TILE + 1, room.y * TILE + 1, room.w * TILE - 2, room.h * TILE - 2);
      ctx.fillStyle = room.trim;
      ctx.fillRect(room.x * TILE, room.y * TILE, room.w * TILE, 8);
      ctx.fillStyle = "#fff8e7";
      ctx.font = "5px monospace";
      ctx.fillText(room.name, room.x * TILE + 3, room.y * TILE + 6);
    }

    drawFurniture(ctx);

    const door = tileToPx(ENTRANCE);
    ctx.fillStyle = "#6e1423";
    ctx.fillRect(door.x - 10, door.y - 6, 20, 12);
    ctx.fillStyle = "#f4d35e";
    ctx.fillRect(door.x - 8, door.y - 4, 16, 8);

    for (const [key, desk] of Object.entries(DESKS)) {
      const working = Boolean(this.avatars[desk.agent]?.work);
      drawDeskSet(ctx, desk, working);
      if (this.hover === key) {
        const p = tileToPx(desk.tile);
        ctx.strokeStyle = "#f4d35e";
        ctx.strokeRect(p.x - 10, p.y - 18, 20, 26);
      }
    }

    const people = Object.values(this.avatars).sort((a, b) => a.y - b.y);
    for (const avatar of people) {
      drawAvatar(ctx, avatar.character, avatar.x, avatar.y, avatar.status, avatar.facing, avatar.phase);
    }

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
    const x = ((ev.clientX - rect.left) / rect.width) * COLS * TILE;
    const y = ((ev.clientY - rect.top) / rect.height) * ROWS * TILE;
    return { x, y };
  }

  _hitDesk(x, y) {
    for (const [key, desk] of Object.entries(DESKS)) {
      const p = tileToPx(desk.tile);
      if (Math.abs(x - p.x) < 12 && Math.abs(y - p.y) < 16) return key;
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
    this.hover = this._hitDesk(x, y);
  }

  _click(ev) {
    const { x, y } = this._pos(ev);
    const env = this._hitEnvelope(x, y);
    if (env && env.doc_id) {
      this.onSelect(this.runs.get(env.doc_id) || { doc_id: env.doc_id, filename: env.label });
      return;
    }
    const person = this._hitAvatar(x, y);
    if (person) {
      this.onSelect(person.work || { desk: person.deskKey, agent: person.agent, filename: person.label, thought: person.thought });
      return;
    }
    const deskKey = this._hitDesk(x, y);
    if (!deskKey) return;
    const desk = DESKS[deskKey];
    const run = [...this.runs.values()].find((r) => r.desk === deskKey);
    this.onSelect(run || { desk: deskKey, agent: desk.agent, filename: desk.label });
  }
}
