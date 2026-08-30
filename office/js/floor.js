import { CAST, ROSTER_CAST } from "./cast.js";

export const TILE = 16;
export const COLS = 40;
export const ROWS = 24;
export const SCALE = 2;

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
  "desk-boss": { tile: [4, 4], agent: "boss", label: "Michael" },
  "desk-reception": { tile: [15, 3], agent: "sorter", label: "Pam" },
  "desk-reception-2": { tile: [20, 3], agent: "sorter_reviewer", label: "Kelly" },
  "desk-judge": { tile: [30, 3], agent: "judge", label: "Oscar" },
  "desk-arbiter": { tile: [35, 3], agent: "arbiter", label: "Stanley" },
  "desk-archive": { tile: [4, 12], agent: "archivist", label: "Creed" },
  "desk-report": { tile: [34, 12], agent: "reporter", label: "Ryan" },
  "desk-contracts": { tile: [4, 19], agent: "contracts_specialist", label: "Dwight" },
  "desk-corporate": { tile: [12, 19], agent: "corporate_records_specialist", label: "Angela" },
  "desk-correspondence": { tile: [25, 19], agent: "correspondence_specialist", label: "Jim" },
  "desk-compliance": { tile: [30, 19], agent: "compliance_specialist", label: "Toby" },
  "desk-claims": { tile: [35, 19], agent: "insurance_claims_specialist", label: "Meredith" },
};

export const ENTRANCE = [19, 22];

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

function drawAvatar(ctx, character, px, py, status) {
  const recipe = CAST[character] || CAST.pam;
  const [sr, sg, sb] = hexToRgb(recipe.skin);
  const [hr, hg, hb] = hexToRgb(recipe.hair);
  const [cr, cg, cb] = hexToRgb(recipe.shirt);
  const x = Math.round(px - 6);
  const y = Math.round(py - 14);
  ctx.fillStyle = `rgb(${hr},${hg},${hb})`;
  if (recipe.hairStyle !== "bald") ctx.fillRect(x + 2, y, 8, 3);
  if (recipe.hairStyle === "bun") ctx.fillRect(x + 4, y - 2, 4, 2);
  if (recipe.hairStyle === "frame") ctx.fillRect(x + 1, y + 3, 2, 6);
  ctx.fillStyle = `rgb(${sr},${sg},${sb})`;
  ctx.fillRect(x + 3, y + 3, 6, 5);
  ctx.fillStyle = `rgb(${cr},${cg},${cb})`;
  ctx.fillRect(x + 2, y + 8, 8, 6);
  ctx.fillStyle = "#1a1320";
  ctx.fillRect(x + 4, y + 5, 1, 1);
  ctx.fillRect(x + 7, y + 5, 1, 1);
  ctx.fillRect(x + 3, y + 14, 3, 4);
  ctx.fillRect(x + 6, y + 14, 3, 4);
  if (status === "working" || status === "thinking") {
    ctx.fillStyle = "#dcab3c";
    ctx.fillRect(x + 9, y - 4, 6, 5);
    ctx.fillStyle = "#1a1320";
    ctx.fillRect(x + 10, y - 2, 1, 1);
    ctx.fillRect(x + 12, y - 2, 1, 1);
  }
}

export class OfficeFloor {
  constructor(canvas, onSelect) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onSelect = onSelect;
    this.runs = new Map();
    this.envelopes = [];
    this.busy = {};
    this.lastDesk = {};
    this.t = 0;
    this.hover = null;
    canvas.addEventListener("click", (ev) => this._click(ev));
    canvas.addEventListener("mousemove", (ev) => this._hover(ev));
    requestAnimationFrame((now) => this._tick(now));
  }

  applySnapshot(runs) {
    const seen = new Set();
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
      this.busy[DESKS[desk]?.agent] = run.stage === "archived" || run.stage === "failed" ? "idle" : "working";
      this.lastDesk[run.doc_id] = desk;
    }
    for (const id of [...this.runs.keys()]) {
      if (!seen.has(id)) {
        const gone = this.runs.get(id);
        if (gone && gone.stage !== "archived" && gone.stage !== "failed") this.runs.delete(id);
      }
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
        const path = (x >= 10 && x <= 29 && y >= 8 && y <= 16) || (y >= 21);
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

    const door = tileToPx(ENTRANCE);
    ctx.fillStyle = "#6e1423";
    ctx.fillRect(door.x - 10, door.y - 6, 20, 12);
    ctx.fillStyle = "#f4d35e";
    ctx.fillRect(door.x - 8, door.y - 4, 16, 8);

    for (const [key, desk] of Object.entries(DESKS)) {
      const p = tileToPx(desk.tile);
      ctx.fillStyle = "#8b6f47";
      ctx.fillRect(p.x - 8, p.y - 4, 16, 10);
      ctx.fillStyle = "#f4e9c7";
      ctx.fillRect(p.x - 7, p.y - 3, 14, 4);
      const character = ROSTER_CAST[desk.agent];
      const status = this.busy[desk.agent] || "idle";
      drawAvatar(ctx, character, p.x, p.y - 2, status);
      if (this.hover === key) {
        ctx.strokeStyle = "#f4d35e";
        ctx.strokeRect(p.x - 10, p.y - 18, 20, 26);
      }
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
    const deskKey = this._hitDesk(x, y);
    if (!deskKey) return;
    const desk = DESKS[deskKey];
    const run = [...this.runs.values()].find((r) => r.desk === deskKey);
    this.onSelect(run || { desk: deskKey, agent: desk.agent, filename: desk.label });
  }
}
