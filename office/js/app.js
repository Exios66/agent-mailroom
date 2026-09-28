import { OfficeFloor } from "./floor.js?v=mailroom10";
import { CAST, ROSTER_CAST } from "./cast.js?v=mailroom10";
import { connectWS, getJSON, getToken, postJSON, setToken, uploadFile } from "./api.js?v=mailroom10";
import { HistoryView } from "./history.js?v=mailroom10";

/* ------------------------------------------------------------------ utils */

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}
const esc = escapeHtml;

/** Only hex colours reach a style attribute (stamps / hive acts come from the API). */
function safeColor(value, fallback = "#a09f9f") {
  return /^#[0-9a-f]{3,8}$/i.test(String(value || "")) ? value : fallback;
}

function pct(value) {
  const n = Number(value);
  return value != null && Number.isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}

function errText(err) {
  return err?.detail || err?.message || String(err);
}

/* ------------------------------------------------------------------ state */

const state = {
  tab: "floor",
  meta: null,
  metaAt: 0,
  docClasses: ["contract", "merger_agreement", "corporate_record", "correspondence", "insurance_claim"],
  subclasses: {},
  archiveReconsiderOnly: false,
  inFlight: false,
  errors: new Map(),
  logLines: [],
  lastFloor: null,
  lastOps: null,
  lastHealth: null,
};

const TAB_TITLES = {
  floor: "Command Center",
  inbox: "Inbox Hopper",
  review: "Review Siding",
  archive: "Archive Shelves",
  failed: "Returns Tray",
  matters: "Matter Index",
  datasets: "Hub Datasets",
  topics: "Floor Briefs",
  hive: "Hive Board",
  metrics: "Floor Metrics",
  history: "Run History",
  console: "Event Console",
};

/* ------------------------------------------------------- announce / toast */

function announce(message) {
  const el = $("live-status");
  if (el) el.textContent = message;
}

function toast(message, kind = "info") {
  const region = $("toasts");
  if (!region) return;
  const el = document.createElement("div");
  el.className = `toast${kind === "error" ? " error" : ""}`;
  el.textContent = message;
  region.appendChild(el);
  while (region.children.length > 4) region.firstChild.remove();
  setTimeout(() => el.remove(), kind === "error" ? 8000 : 4000);
}

/** Toast an endpoint failure once per outage, not on every poll. */
function reportError(key, err) {
  const message = errText(err);
  if (state.errors.get(key) !== message) {
    state.errors.set(key, message);
    toast(`${key}: ${message}`, "error");
    appendLog({ type: "error", subject: `${key}: ${message}` });
  }
}

function clearError(key) {
  state.errors.delete(key);
}

/**
 * Busy/done/error wrapper for every user action: disables the trigger,
 * reports the outcome inline (and via toast on failure), never throws.
 */
async function runAction(button, statusEl, fn, okMessage) {
  if (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  if (statusEl) {
    statusEl.className = "inline-status";
    statusEl.textContent = "Working…";
  }
  try {
    const result = await fn();
    const message = typeof okMessage === "function" ? okMessage(result) : okMessage;
    if (statusEl) {
      statusEl.className = "inline-status ok";
      statusEl.textContent = message || "";
    }
    if (message) announce(message);
    return result ?? {};
  } catch (err) {
    const message = errText(err);
    if (statusEl) {
      statusEl.className = "inline-status error";
      statusEl.textContent = message;
    }
    toast(message, "error");
    appendLog({ type: "error", subject: message });
    return undefined;
  } finally {
    if (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }
}

/* ------------------------------------------------------ render with guards */

const signatures = new WeakMap();

/**
 * Re-render a container only when its markup would change, and never while
 * someone is typing in it (focused field or an edited form). Open <details>
 * keep their state across renders via ``data-key``. The old poll rebuilt
 * every panel every 2.5 s, wiping half-typed review notes.
 */
function renderInto(container, html, wire) {
  if (!container) return false;
  if (signatures.get(container) === html) return false;
  const active = document.activeElement;
  if (active && container.contains(active) && active.matches("input, textarea, select")) return false;
  if (container.querySelector("[data-dirty='1']")) return false;
  const open = new Set(
    [...container.querySelectorAll("details[open][data-key]")].map((el) => el.dataset.key),
  );
  container.innerHTML = html;
  signatures.set(container, html);
  for (const el of container.querySelectorAll("details[data-key]")) {
    if (open.has(el.dataset.key)) el.open = true;
  }
  if (wire) wire(container);
  return true;
}

function emptyState(message) {
  return `<p class="state">${esc(message)}</p>`;
}

function errorState(message) {
  return `<p class="state error" role="alert">${esc(message)}</p>`;
}

function chip(text, kind = "") {
  return text ? `<span class="chip${kind ? ` ${kind}` : ""}">${esc(text)}</span>` : "";
}

/* --------------------------------------------------------------- the floor */

const floor = new OfficeFloor($("floor"), (item) => {
  if (item?.tray && item.tab) switchTab(item.tab);
  else switchTab("floor");
  showInspect(item);
});
window.__MAILROOM_FLOOR__ = floor;

/* --------------------------------------------------------------------- tabs */

function tabButtons() {
  return [...document.querySelectorAll("[role='tab'][data-tab]")];
}

function switchTab(name, { focus = false } = {}) {
  if (!TAB_TITLES[name]) return;
  const changed = state.tab !== name;
  state.tab = name;
  for (const btn of tabButtons()) {
    const selected = btn.dataset.tab === name;
    btn.classList.toggle("active", selected);
    btn.setAttribute("aria-selected", selected ? "true" : "false");
    btn.tabIndex = selected ? 0 : -1;
    if (selected && focus) btn.focus();
  }
  for (const view of document.querySelectorAll(".view")) {
    view.classList.toggle("active", view.id === `view-${name}`);
  }
  document.body.dataset.panel = name;
  $("panel-title").textContent = TAB_TITLES[name];
  if (!changed) return;
  if (name === "history") HistoryView.refresh().catch((err) => reportError("history", err));
  if (name === "console") renderConsole();
  refreshPanel(name);
}

function wireTabs() {
  const buttons = tabButtons();
  buttons.forEach((btn, i) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    btn.addEventListener("keydown", (ev) => {
      let next = null;
      if (ev.key === "ArrowRight") next = buttons[(i + 1) % buttons.length];
      else if (ev.key === "ArrowLeft") next = buttons[(i - 1 + buttons.length) % buttons.length];
      else if (ev.key === "Home") next = buttons[0];
      else if (ev.key === "End") next = buttons[buttons.length - 1];
      if (next) {
        ev.preventDefault();
        switchTab(next.dataset.tab, { focus: true });
      }
    });
  });
}

/* ---------------------------------------------------------------- inspector */

let inspectSeq = 0;

function showInspect(item) {
  const inspect = $("inspect");
  if (!item) {
    inspect.innerHTML = emptyState("Nothing selected.");
    return;
  }
  const seq = ++inspectSeq;
  renderInspectCard(item);
  if (item.doc_id) {
    getJSON(`/v1/inspect/${encodeURIComponent(item.doc_id)}`)
      .then((payload) => {
        if (seq !== inspectSeq) return; // a newer selection won the race
        renderInspectCard({
          ...item,
          ...payload.document,
          _audit: payload.audit,
          _source: payload.source,
          _conflict: payload.conflict,
          _spans: payload.spans,
        });
      })
      .catch((err) => {
        if (seq !== inspectSeq) return;
        inspect.insertAdjacentHTML("beforeend", errorState(`Could not load ${item.doc_id}: ${errText(err)}`));
      });
  }
}

function renderInspectCard(item) {
  const inspect = $("inspect");
  const title = item.filename || item.original_filename || item.agent || "Selection";
  const pile = (item.documents || []).map((row) =>
    `<li><button type="button" class="linkish" data-doc-link="${esc(row.doc_id)}">${esc(row.filename || row.original_filename || row.doc_id)}</button> ${chip(row.stage || row.bin)}</li>`,
  ).join("");
  const chips = [
    item.documents ? chip(`${item.tray} tray`) : "",
    chip(item.stage),
    item.bin && item.bin !== item.stage ? chip(item.bin) : "",
    chip(item.doc_type, "info"),
    chip(item.doc_subclass),
    item.needs_reconsideration ? chip("RECONSIDER", "review") : "",
    item.conflict_detected ? chip("conflict", "fail") : "",
    item.needs_human ? chip("needs human", "review") : "",
    item.failure_class ? chip(item.failure_class, "fail") : "",
    chip(item.agent),
  ].join("");
  const causes = (item.review_causes || []).map((c) => chip(c)).join("");
  const path = (item.routing_path || []).join(" → ");
  const fields = item.extracted_data
    ? `<details class="card" open><summary>Extracted fields</summary><pre>${esc(JSON.stringify(item.extracted_data, null, 2))}</pre></details>`
    : "";
  const spans = (item._spans || []).map((span) =>
    `<li><b>${esc(span.name)}</b> <span class="muted">${esc(span.observation_type || "")} · ${Number(span.latency_ms || 0).toFixed(0)} ms</span></li>`,
  ).join("");
  const spanBlock = spans ? `<details class="card"><summary>Trace spans (${(item._spans || []).length})</summary><ol class="audit">${spans}</ol></details>` : "";
  const audit = item._audit
    ? `<details class="card"><summary>Audit chain · ${item._audit.chain_valid ? "valid" : "BROKEN"} · ${Number(item._audit.chain_length) || 0} links</summary>
       <ol class="audit">${(item._audit.entries || []).slice(-10).map((e) =>
         `<li><b>${esc(e.event)}</b> ${esc(e.actor)} <span class="muted">${esc(e.timestamp || "")}</span></li>`,
       ).join("")}</ol></details>`
    : "";
  const source = item._source
    ? `<details class="card"><summary>Source · ${esc(item._source.bin || "")}</summary><pre>${esc(item._source.text || "(no readable text)")}</pre></details>`
    : "";
  const conflict = item._conflict ? `<p class="fail-text">${esc(item._conflict.reason || "matter conflict")}</p>` : "";
  const confidence = item.classification_confidence != null
    ? `<p class="meta-line">classify ${pct(item.classification_confidence)} · extract ${pct(item.extraction_confidence)}${item.judge_verdict ? ` · judge ${esc(item.judge_verdict)}` : ""}</p>`
    : "";
  inspect.innerHTML = `
    <article class="card selected" aria-label="Inspector">
      <h3>${esc(title)}</h3>
      <div>${chips}${causes}</div>
      <p class="meta-line">${esc(item.doc_id || item.desk || "")}${item.matter_id ? ` · ${esc(item.matter_id)}` : ""}</p>
      ${confidence}
      ${path ? `<p class="meta-line">${esc(path)}</p>` : ""}
      ${item.thought ? `<p>${esc(item.thought)}</p>` : ""}
      ${item.escalation_reason ? `<p>${esc(item.escalation_reason)}</p>` : ""}
      ${conflict}
      ${item.report ? `<p>${esc(item.report)}</p>` : ""}
      ${pile ? `<ul class="audit">${pile}</ul>` : ""}
    </article>
    ${fields}${spanBlock}${audit}${source}
    ${reviewActionsHtml(item)}`;
  wireReviewActions(inspect);
  wireDocLinks(inspect);
}

function wireDocLinks(root) {
  root.querySelectorAll("[data-doc-link]").forEach((link) => {
    link.addEventListener("click", (ev) => {
      ev.stopPropagation();
      switchTab("floor");
      showInspect({ doc_id: link.dataset.docLink, filename: link.textContent });
      $("inspect")?.scrollIntoView({ block: "start" });
    });
  });
}

/* ------------------------------------------------------------ review desk */

function subclassDatalist(docType) {
  const options = state.subclasses[docType] || [];
  return `<datalist id="subclass-${esc(docType)}">${options.map((s) => `<option value="${esc(s)}"></option>`).join("")}</datalist>`;
}

function reviewActionsHtml(doc) {
  const parked = doc.stage === "review";
  if (!doc.doc_id || (!parked && !doc.needs_human)) return "";
  const dtype = doc.doc_type && state.docClasses.includes(doc.doc_type) ? doc.doc_type : state.docClasses[0];
  // Reject goes out as disposition=resume: disposition=complete requires
  // decision=approved (llm-mailroom contract), so the old Reject button
  // (rejected + complete) could only ever get a 400.
  const buttons = parked
    ? `<button type="button" class="btn primary" data-act="approved" data-disp="resume">Approve &amp; resume</button>
       <button type="button" class="btn" data-act="approved" data-disp="complete">Complete</button>
       <button type="button" class="btn" data-act="approved" data-disp="record">Record</button>
       <button type="button" class="btn" data-act="approved" data-disp="requeue">Requeue</button>
       <button type="button" class="btn danger" data-act="rejected" data-disp="resume">Reject</button>`
    : `<button type="button" class="btn" data-act="approved" data-disp="record">Record note</button>
       <button type="button" class="btn" data-act="approved" data-disp="requeue">Requeue</button>`;
  return `
    <form class="card review-actions" data-doc="${esc(doc.doc_id)}" aria-label="Resolve ${esc(doc.original_filename || doc.filename || doc.doc_id)}">
      <h3>Resolve</h3>
      <label>Doc type
        <select class="dtype">
          ${state.docClasses.map((t) => `<option value="${esc(t)}"${t === dtype ? " selected" : ""}>${esc(t)}</option>`).join("")}
        </select>
      </label>
      ${subclassDatalist(dtype)}
      <label>Subclass <input class="subclass" list="subclass-${esc(dtype)}" value="${esc(doc.doc_subclass || "")}" placeholder="pick or type" autocomplete="off"></label>
      <label>Notes <input class="notes" placeholder="operator notes" autocomplete="off"></label>
      ${parked ? `<label>Extracted JSON (used by Complete) <textarea class="extracted" rows="5" spellcheck="false">${esc(JSON.stringify(doc.extracted_data || {}, null, 2))}</textarea></label>` : ""}
      <div class="row">${buttons}</div>
      <p class="inline-status" role="status"></p>
    </form>`;
}

const RESOLVE_DONE = {
  resumed: "Approved and resumed",
  archived: "Completed and archived",
  failed: "Rejected to the returns tray",
  recorded: "Note recorded",
  requeued: "Requeued as a fresh run",
};

function wireReviewActions(root) {
  root.querySelectorAll("form.review-actions").forEach((form) => {
    const docId = form.dataset.doc;
    const statusEl = form.querySelector(".inline-status");
    form.addEventListener("submit", (ev) => ev.preventDefault());
    form.addEventListener("input", () => { form.dataset.dirty = "1"; });
    form.querySelectorAll("button[data-act]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        let extracted = null;
        const raw = form.querySelector(".extracted")?.value;
        if (btn.dataset.disp === "complete" && raw) {
          try {
            extracted = JSON.parse(raw);
          } catch {
            statusEl.className = "inline-status error";
            statusEl.textContent = "Extracted JSON is not valid JSON.";
            return;
          }
        }
        const result = await runAction(btn, statusEl, () => postJSON(`/v1/review/${encodeURIComponent(docId)}/resolve`, {
          decision: btn.dataset.act,
          disposition: btn.dataset.disp,
          doc_type: form.querySelector(".dtype")?.value || null,
          doc_subclass: form.querySelector(".subclass")?.value || null,
          notes: form.querySelector(".notes")?.value || null,
          extracted_data: extracted,
        }), (res) => RESOLVE_DONE[res?.status] || "Done");
        if (result) {
          delete form.dataset.dirty;
          toast(`${RESOLVE_DONE[result.status] || "Done"} · ${docId.slice(0, 8)}`);
          refresh();
        }
      });
    });
    const dtypeSel = form.querySelector(".dtype");
    const subclassInput = form.querySelector(".subclass");
    dtypeSel?.addEventListener("change", () => {
      const listId = `subclass-${dtypeSel.value}`;
      subclassInput?.setAttribute("list", listId);
      if (!document.getElementById(listId)) form.insertAdjacentHTML("beforeend", subclassDatalist(dtypeSel.value));
    });
  });
}

function docCard(doc, body = "", { stage } = {}) {
  const name = doc.original_filename || doc.filename || doc.doc_id;
  return `
    <div class="card" data-doc="${esc(doc.doc_id)}" data-stage="${esc(stage || doc.stage || "")}" tabindex="0" aria-label="Inspect ${esc(name)}">
      <h3>${esc(name)}</h3>
      ${body}
    </div>`;
}

function bindInspectCards(root) {
  root.querySelectorAll(".card[data-doc]").forEach((card) => {
    const open = () => {
      const id = card.dataset.doc;
      if (!id) return;
      switchTab("floor");
      showInspect({ doc_id: id, filename: card.querySelector("h3")?.textContent || id, stage: card.dataset.stage });
      $("inspect")?.scrollIntoView({ block: "start" });
    };
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button,input,select,textarea,label,details,a,form")) return;
      open();
    });
    card.addEventListener("keydown", (ev) => {
      if (ev.target !== card) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        open();
      }
    });
  });
}

function renderReview(docs) {
  const html = docs.length
    ? docs.map((doc) => `
      <div class="card" data-review="${esc(doc.doc_id)}">
        <h3>${esc(doc.original_filename)}</h3>
        ${chip(doc.doc_type || "unknown", "review")}
        ${(doc.review_causes || []).map((c) => chip(c)).join("")}
        <p class="muted">${esc(doc.escalation_reason || "needs a human")}</p>
        <p class="meta-line">${esc(doc.matter_id || "")} · ${esc(doc.doc_id)}</p>
        <div class="row"><button type="button" class="btn ghost" data-doc-link="${esc(doc.doc_id)}">Inspect</button></div>
        ${reviewActionsHtml({ ...doc, stage: "review" })}
        <details data-key="src-${esc(doc.doc_id)}"><summary>Read source</summary><pre class="source-pane" data-src="${esc(doc.doc_id)}">loading…</pre></details>
      </div>`).join("")
    : emptyState("No documents on the siding. The floor is clearing itself.");
  renderInto($("review-list"), html, (root) => {
    wireReviewActions(root);
    wireDocLinks(root);
    root.querySelectorAll("details[data-key^='src-']").forEach((el) => {
      const load = async () => {
        if (!el.open) return;
        const pane = el.querySelector(".source-pane");
        if (!pane || pane.dataset.ready) return;
        try {
          const src = await getJSON(`/v1/documents/${encodeURIComponent(pane.dataset.src)}/source`);
          pane.textContent = (src.text || "(no readable text)") + (src.truncated ? "\n… (truncated)" : "");
          pane.dataset.ready = "1";
        } catch (err) {
          pane.textContent = errText(err);
        }
      };
      el.addEventListener("toggle", load);
      load();
    });
  });
}

/* ----------------------------------------------------------- list panels */

function renderLookup(docs) {
  const hits = $("lookup-hits");
  hits.innerHTML = docs.length
    ? docs.map((doc) => docCard(doc, `${chip(doc.stage)}${chip(doc.doc_type || "unknown", "info")}<p class="meta-line">${esc(doc.matter_id)} · ${esc(doc.doc_id)}</p>`)).join("")
    : emptyState("No filings match.");
  bindInspectCards(hits);
}

function renderInbox(queue, classified) {
  const hopper = queue.inbox || queue.queued || [];
  const processing = queue.processing || [];
  const snaps = classified || [];
  const html = !hopper.length && !processing.length && !snaps.length
    ? emptyState("The hopper is empty. Upload a filing or drop the demo pile.")
    : [
      hopper.length ? `<h3 class="section-title">Hopper · ${hopper.length}</h3>` : "",
      ...hopper.map((row) => docCard({ ...row, original_filename: row.filename }, `${chip("inbox")}<p class="meta-line">${esc(row.matter_id || "")} · ${esc(row.source || "")}</p>`)),
      processing.length ? `<h3 class="section-title">At a desk · ${processing.length}</h3>` : "",
      ...processing.map((row) => docCard(row, `${chip(row.stage || "processing", "info")}<p class="meta-line">${esc(row.matter_id || "")} · ${esc(row.bin || "")}</p>`)),
      snaps.length ? `<h3 class="section-title">Classified snapshots</h3>` : "",
      ...snaps.slice(0, 8).map((row) => docCard(row, `${chip("classified")}<p class="meta-line">${esc(row.doc_type || row.classified_type || "")} snapshot</p>`)),
    ].join("");
  renderInto($("inbox-list"), html, bindInspectCards);
}

function renderArchive(docs) {
  const html = docs.length
    ? docs.map((doc) => docCard(doc, `
        ${chip(doc.doc_type || "unknown", "info")}
        ${doc.needs_reconsideration ? chip("RECONSIDER", "review") : chip("filed", "ok")}
        ${(doc.review_causes || []).map((c) => chip(c)).join("")}
        <p class="meta-line">${esc(doc.matter_id)} · ${esc(doc.doc_id)}</p>
        <div class="row">
          ${doc.needs_reconsideration ? `<button type="button" class="btn" data-requeue="${esc(doc.doc_id)}">Requeue</button>` : ""}
          <button type="button" class="btn" data-verify="${esc(doc.doc_id)}">Verify chain</button>
        </div>
        <p class="inline-status" role="status"></p>`, { stage: doc.stage || "archived" })).join("")
    : emptyState(state.archiveReconsiderOnly ? "No filings flagged for reconsideration." : "Creed's shelves are empty.");
  renderInto($("archive-list"), html, (list) => {
    bindInspectCards(list);
    list.querySelectorAll("[data-requeue]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const status = btn.closest(".card").querySelector(".inline-status");
        const result = await runAction(btn, status, () => postJSON(`/v1/archive/${encodeURIComponent(btn.dataset.requeue)}/requeue`, {}),
          (res) => `Requeued as ${res.doc_id}`);
        if (result) refresh();
      });
    });
    list.querySelectorAll("[data-verify]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const status = btn.closest(".card").querySelector(".inline-status");
        await runAction(btn, status, () => getJSON(`/v1/archive/${encodeURIComponent(btn.dataset.verify)}/verify`),
          (res) => `${res.chain_valid ? "VALID" : "BROKEN"} · ${res.chain_length} links`);
      });
    });
  });
}

function renderFailed(docs) {
  const html = docs.length
    ? docs.map((doc) => {
      const superseded = doc.review_decision === "requeued";
      return docCard(doc, `
        ${chip(superseded ? "superseded" : "failed", superseded ? "" : "fail")}
        ${doc.failure_class ? chip(doc.failure_class, "fail") : ""}
        ${(doc.review_causes || []).map((c) => chip(c)).join("")}
        <p class="muted">${esc(doc.escalation_reason || "rejected")}</p>`, { stage: "failed" });
    }).join("")
    : emptyState("No returns. Rejected or aborted filings land here.");
  renderInto($("failed-list"), html, bindInspectCards);
}

function renderMatters(data) {
  const rows = data.matters || [];
  const html = rows.length
    ? rows.map((row) => `
      <div class="card">
        <h3>${esc(row.matter_id)}</h3>
        ${chip(`${Number(row.document_count) || 0} docs`)}
        ${chip(`${Number(row.review_count) || 0} review`, Number(row.review_count) ? "review" : "")}
        ${chip(`${Number(row.archived_count) || 0} archived`, "ok")}
        ${Number(row.failed_count) ? chip(`${Number(row.failed_count)} returns`, "fail") : ""}
        <details data-key="matter-${esc(row.matter_id)}" data-open="${esc(row.matter_id)}"><summary>Documents</summary><ul class="audit matter-docs"><li class="muted">loading…</li></ul></details>
      </div>`).join("")
    : emptyState("No matters yet. Upload a filing or pull a corpus.");
  renderInto($("matter-list"), html, (list) => {
    list.querySelectorAll("details[data-open]").forEach((el) => {
      const load = async () => {
        if (!el.open) return;
        const pane = el.querySelector(".matter-docs");
        try {
          const payload = await getJSON(`/v1/matters/${encodeURIComponent(el.dataset.open)}`);
          pane.innerHTML = (payload.documents || []).map((doc) =>
            `<li><button type="button" class="linkish" data-doc-link="${esc(doc.doc_id)}">${esc(doc.original_filename)}</button> ${chip(doc.stage)}</li>`,
          ).join("") || `<li class="muted">No documents.</li>`;
          wireDocLinks(pane);
        } catch (err) {
          pane.innerHTML = `<li class="fail-text">${esc(errText(err))}</li>`;
        }
      };
      el.addEventListener("toggle", load);
      load();
    });
  });
}

function renderHive(data) {
  const acts = floor.hiveActs || {};
  const board = data.board?.content || "";
  const boardBlock = board
    ? `<details class="card" data-key="board" open><summary>Blackboard</summary><pre class="hive-board">${esc(board)}</pre></details>`
    : "";
  const cards = Object.entries(data.registry || {}).map(([name, meta]) => {
    const character = ROSTER_CAST[name];
    const mail = (data.inboxes?.[name] || []).slice(0, 3);
    return `<div class="card">
      <h3>${esc(CAST[character]?.name || name)} · ${esc(meta.role)}</h3>
      <p class="meta-line">${esc(name)} · inbox ${Number(meta.inbox_count) || 0}</p>
      ${mail.map((m) => `<span class="chip"><span class="swatch" style="background:${safeColor(acts[m.act], "#fff8e7")}"></span>${esc(m.act)} · ${esc(m.subject)}</span>`).join("")}
    </div>`;
  });
  renderInto($("hive-list"), (boardBlock + cards.join("")) || emptyState("The hive is quiet."));
}

function renderTopics(topics) {
  const html = topics.length
    ? topics.map((topic) => {
      const actions = topic.status === "queued"
        ? `<button type="button" class="btn" data-launch="${esc(topic.topic_id)}">Launch</button>`
        : topic.status === "done" ? "" : `<button type="button" class="btn" data-complete="${esc(topic.topic_id)}">Mark done</button>`;
      const body = String(topic.body || "");
      // Slice the raw text, then escape (slicing escaped text cut entities in half).
      return `
      <div class="card">
        <h3>${esc(topic.subject)}</h3>
        ${chip(topic.status, topic.status === "done" ? "ok" : "review")}
        ${chip(topic.route_to)}
        <p class="meta-line">${esc(topic.matter_id)}</p>
        ${body ? `<p>${esc(body.length > 280 ? `${body.slice(0, 279)}…` : body)}</p>` : ""}
        ${actions ? `<div class="row">${actions}</div>` : ""}
      </div>`;
    }).join("")
    : emptyState("No topics yet. Queue a brief for later or launch it onto a desk.");
  renderInto($("topic-list"), html, (list) => {
    list.querySelectorAll("[data-launch]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (await runAction(btn, $("topic-status"), () => postJSON(`/v1/topics/${encodeURIComponent(btn.dataset.launch)}/launch`, {}), "Brief launched")) refresh();
      });
    });
    list.querySelectorAll("[data-complete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (await runAction(btn, $("topic-status"), () => postJSON(`/v1/topics/${encodeURIComponent(btn.dataset.complete)}/complete`, {}), "Brief closed")) refresh();
      });
    });
  });
}

function renderDatasets(data) {
  const select = $("dataset-corpus");
  const rows = data.pipeline || [];
  if (!select.dataset.ready && rows.length) {
    select.innerHTML = rows.map((c) =>
      `<option value="${esc(c.slug)}">${esc(c.slug)} · ${c.n_docs != null ? Number(c.n_docs).toLocaleString() : "?"} rows</option>`,
    ).join("");
    select.dataset.ready = "1";
    if (rows.some((c) => c.slug === "docclass-pilot")) select.value = "docclass-pilot";
  }
  renderInto($("dataset-list"), rows.map((c) => `
    <div class="card">
      <h3>${esc(c.slug)}</h3>
      ${chip(c.id, "info")}${c.revision ? chip(`rev ${c.revision}`) : ""}
      <p class="muted">${esc(c.note || c.role)}</p>
      <p class="meta-line">${esc((c.classes || []).join(", "))}</p>
    </div>`).join("") || emptyState("No pipeline corpora configured."));
}

function stat(label, value, { small = false } = {}) {
  return `<div class="stat"><div class="label">${esc(label)}</div><div class="value${small ? " small" : ""}">${esc(value)}</div></div>`;
}

function renderMetrics(floorData, health, ops) {
  const llm = health?.checks?.llm || ops?.llm || {};
  const active = llm.active || "mock";
  const requested = llm.requested || active;
  const lamp = health?.checks?.watcher || ops?.watcher?.lamp || "ok";
  const bins = ops?.bins || {};
  const classes = Object.entries(ops?.classes || {});
  const stages = Object.entries(ops?.documents || {});
  const html = `
    <div class="stat-grid">
      ${stat("Documents", floorData?.count ?? 0)}
      ${stat("Inbox", bins.inbox ?? 0)}
      ${stat("Review", bins.review ?? 0)}
      ${stat("Archived", bins.archived ?? 0)}
      ${stat("Returns", bins.failed ?? 0)}
      ${stat("Stuck > 15 min", ops?.stuck_documents ?? 0)}
      ${stat("Reconsider", ops?.reconsider ?? 0)}
      ${stat("Watcher", lamp, { small: true })}
      ${stat("Harness", requested === active ? active : `${requested} → ${active}`, { small: true })}
      ${stat("Model", llm.model || "—", { small: true })}
    </div>
    ${classes.length ? `<details class="card" data-key="classes" open><summary>By class</summary><table class="data-table"><tbody>${classes.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${Number(v) || 0}</td></tr>`).join("")}</tbody></table></details>` : ""}
    ${stages.length ? `<details class="card" data-key="stages"><summary>By stage</summary><table class="data-table"><tbody>${stages.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${Number(v) || 0}</td></tr>`).join("")}</tbody></table></details>` : ""}`;
  renderInto($("metrics"), html);
}

function renderProviders(data) {
  if (!data) return;
  const harnesses = data.harnesses || [];
  // Columns used to print the harness name twice and never the models.
  renderInto($("providers-panel"), `
    <details class="card" data-key="providers">
      <summary>LLM harnesses · active ${esc(data.active || "")}</summary>
      <p class="meta-line">requested ${esc(data.requested || "")} · model ${esc(data.model || "")} · fallback ${esc(data.fallback || "")}</p>
      <div class="table-scroll"><table class="data-table">
        <thead><tr><th scope="col">Harness</th><th scope="col">Default model</th><th scope="col">Models</th><th scope="col">Configured</th></tr></thead>
        <tbody>
          ${harnesses.map((row) => `
            <tr>
              <td>${esc(row.name || "")}${row.name === data.active ? " (active)" : ""}</td>
              <td>${esc(row.default_model || "—")}</td>
              <td>${esc((row.models || []).join(", ") || "—")}</td>
              <td>${row.configured ? "yes" : "no"}</td>
            </tr>`).join("")}
        </tbody>
      </table></div>
    </details>`);
}

function renderOpsResults(result, kind) {
  const el = $("ops-results");
  if (!el || !result) return;
  if (kind === "sweep") {
    const rows = (result.details || []).map((row) =>
      `<li><button type="button" class="linkish" data-doc-link="${esc(row.doc_id)}">${esc(row.filename || row.doc_id)}</button> ${chip(row.stage)} ${(row.causes || []).map((c) => chip(c)).join("")}</li>`,
    ).join("");
    el.innerHTML = `<details class="card" open><summary>Sweep · ${Number(result.escalated) || 0} escalated · review ${Number(result.review) || 0} · returns ${Number(result.failed) || 0} · reconsider ${Number(result.reconsider) || 0}</summary>
      <ol class="audit">${rows || "<li class='muted'>Nothing to sweep</li>"}</ol></details>`;
  } else {
    // Recover requeues to the inbox (it used to claim "moved to review").
    const rows = (result.recovered || []).map((row) =>
      `<li><button type="button" class="linkish" data-doc-link="${esc(row.doc_id)}">${esc(row.doc_id)}</button> ${chip(`from ${row.from_bin || "?"}`)}</li>`,
    ).join("");
    el.innerHTML = `<details class="card" open><summary>Recover · ${Number(result.count) || 0} stuck filings requeued to the inbox</summary>
      <ol class="audit">${rows || "<li class='muted'>Nothing stuck</li>"}</ol></details>`;
  }
  wireDocLinks(el);
}

function stageKind(stage) {
  if (stage === "review") return "review";
  if (stage === "failed") return "fail";
  if (stage === "archived") return "ok";
  return "info";
}

/** Keyboard/screen-reader mirror of the canvas. */
function renderFloorRuns(runs) {
  const ordered = [...runs].sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))).slice(0, 40);
  const html = ordered.length
    ? ordered.map((run) => `
      <li><button type="button" data-run="${esc(run.doc_id)}" aria-label="${esc(run.filename)}, ${esc(run.stage)}${run.doc_type ? `, ${esc(run.doc_type)}` : ""}">
        <span class="dot" style="background:${safeColor(run.stamp)}" aria-hidden="true"></span>
        <span class="name">${esc(run.filename)}</span>
        ${chip(run.stage, stageKind(run.stage))}
      </button></li>`).join("")
    : `<li>${emptyState("Nothing on the floor yet. Drop the demo pile to watch the office work.")}</li>`;
  renderInto($("floor-runs"), html, (root) => {
    root.querySelectorAll("[data-run]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const run = (state.lastFloor?.runs || []).find((r) => r.doc_id === btn.dataset.run);
        showInspect(run || { doc_id: btn.dataset.run });
        $("inspect")?.scrollIntoView({ block: "start" });
      });
    });
  });
}

/* ----------------------------------------------------------------- console */

function appendLog(event) {
  const when = new Date().toLocaleTimeString([], { hour12: false });
  const type = String(event.type || "event").padEnd(8);
  const what = event.stage || event.act || "";
  const subject = event.filename || event.subject || event.doc_id || "";
  state.logLines.push(`${when} ${type} ${what} ${subject}`.trimEnd());
  if (state.logLines.length > 400) state.logLines.splice(0, state.logLines.length - 400);
  if (state.tab === "console") renderConsole();
}

function renderConsole() {
  const el = $("console-log");
  if (el) el.textContent = state.logLines.slice(-200).join("\n") || "No events yet.";
}

/* ------------------------------------------------------------------- data */

function setBadge(name, count) {
  const el = document.querySelector(`[data-badge="${name}"]`);
  if (!el) return;
  const n = Number(count) || 0;
  el.textContent = n > 99 ? "99+" : String(n);
  el.hidden = n <= 0;
}

function applyMeta(meta) {
  state.meta = meta;
  state.metaAt = Date.now();
  if (Array.isArray(meta.doc_classes) && meta.doc_classes.length) state.docClasses = meta.doc_classes;
  if (meta.subclasses) state.subclasses = meta.subclasses;
  if (meta.hive_acts) floor.setHiveActs(meta.hive_acts);
  wireAuth(meta);
  // Every desk is a valid brief route (the old list hard-coded 7 of 12).
  const route = $("topic-route");
  const agents = Object.keys(meta.agents || {});
  if (route && agents.length && route.options.length !== agents.length && document.activeElement !== route) {
    const current = route.value || "boss";
    route.innerHTML = agents.map((name) => {
      const role = meta.agents[name]?.role;
      return `<option value="${esc(name)}">${esc(name)}${role ? ` · ${esc(role)}` : ""}</option>`;
    }).join("");
    route.value = agents.includes(current) ? current : "boss";
  }
}

function applyStatus(floorData, ops, health) {
  const bins = ops?.bins || {};
  setBadge("inbox", bins.inbox ?? floorData?.inbox_pending ?? 0);
  setBadge("review", bins.review ?? ops?.review_queue ?? floorData?.review_queue ?? 0);
  setBadge("archive", bins.archived ?? floorData?.archived ?? 0);
  setBadge("failed", bins.failed ?? floorData?.failed ?? 0);
  const llm = health?.checks?.llm || ops?.llm || {};
  const active = llm.active || health?.checks?.llm_provider || "mock";
  const requested = llm.requested || active;
  $("provider").textContent = requested !== active ? `${requested}→${active}` : active;
  const lamp = $("lamp");
  const watcher = health?.checks?.watcher || ops?.watcher?.lamp || "ok";
  const down = health?.status === "down" || (!floorData && !ops);
  lamp.dataset.state = down ? "down" : watcher;
  lamp.textContent = down ? "OFFICE UNREACHABLE" : watcher === "ok" ? "SOURCE: LIVE PIPELINE" : `WATCHER ${String(watcher).toUpperCase()}`;
  const inbox = bins.inbox ?? floorData?.inbox_pending ?? 0;
  $("counts").textContent = `${floorData?.count ?? 0} docs · inbox ${inbox} · review ${bins.review ?? 0}`;
}

function settle(key, result, onValue) {
  if (result.status === "fulfilled") {
    clearError(key);
    onValue(result.value);
    return true;
  }
  reportError(key, result.reason);
  return false;
}

async function panelFetch(container, key, fetcher, render) {
  const [result] = await Promise.allSettled([fetcher()]);
  if (result.status === "fulfilled") {
    clearError(key);
    render(result.value);
  } else {
    reportError(key, result.reason);
    // Keep the last good render; only an empty panel gets the error state.
    if (container && !signatures.has(container)) renderInto(container, errorState(`${key}: ${errText(result.reason)}`));
  }
}

async function refreshPanel(tab = state.tab) {
  switch (tab) {
    case "review":
      return panelFetch($("review-list"), "review queue", () => getJSON("/v1/review/queue"), (d) => renderReview(d.documents || []));
    case "inbox":
      return panelFetch($("inbox-list"), "queue",
        async () => {
          const [queue, classified] = await Promise.all([getJSON("/v1/queue"), getJSON("/v1/classified").catch(() => ({ documents: [] }))]);
          return { queue, classified };
        },
        ({ queue, classified }) => renderInbox(queue, classified.documents || []));
    case "archive":
      return panelFetch($("archive-list"), "archive",
        () => getJSON(state.archiveReconsiderOnly ? "/v1/archive?reconsider=true" : "/v1/archive"),
        (d) => renderArchive(d.documents || []));
    case "failed":
      return panelFetch($("failed-list"), "returns", () => getJSON("/v1/failed"), (d) => renderFailed(d.documents || []));
    case "matters":
      return panelFetch($("matter-list"), "matters", () => getJSON("/v1/matters"), renderMatters);
    case "hive":
      return panelFetch($("hive-list"), "hive", () => getJSON("/v1/hive"), renderHive);
    case "topics":
      return panelFetch($("topic-list"), "topics", () => getJSON("/v1/topics"), (d) => renderTopics(d.topics || []));
    case "datasets":
      return panelFetch($("dataset-list"), "datasets", () => getJSON("/v1/datasets"), renderDatasets);
    case "metrics":
      renderMetrics(state.lastFloor, state.lastHealth, state.lastOps);
      return panelFetch($("providers-panel"), "providers", () => getJSON("/v1/providers"), renderProviders);
    case "floor":
      if (state.lastFloor) renderFloorRuns(state.lastFloor.runs || []);
      return undefined;
    default:
      return undefined;
  }
}

/**
 * One poll: floor + status always, then only the visible panel. Every
 * request settles on its own, so one failing endpoint no longer blanks the
 * whole office (the old Promise.all over 15 endpoints did).
 */
async function refresh() {
  if (state.inFlight) return;
  state.inFlight = true;
  try {
    const needMeta = !state.meta || Date.now() - state.metaAt > 30000;
    const [floorRes, opsRes, healthRes, metaRes] = await Promise.allSettled([
      getJSON("/v1/floor"),
      getJSON("/v1/ops/status"),
      getJSON("/v1/health"),
      needMeta ? getJSON("/v1/meta") : Promise.resolve(null),
    ]);
    settle("meta", metaRes, (meta) => { if (meta) applyMeta(meta); });
    const okHealth = settle("health", healthRes, (health) => { state.lastHealth = health; });
    const okOps = settle("ops status", opsRes, (ops) => { state.lastOps = ops; });
    const okFloor = settle("floor", floorRes, (floorData) => {
      state.lastFloor = floorData;
      floor.applySnapshot(floorData.runs || [], floorData.bins);
    });
    applyStatus(okFloor ? state.lastFloor : null, okOps ? state.lastOps : null, okHealth ? state.lastHealth : null);
    await refreshPanel(state.tab);
  } finally {
    state.inFlight = false;
  }
}

/* ------------------------------------------------------------------ auth */

function wireAuth(meta) {
  const gate = $("auth-gate");
  if (!gate) return;
  gate.hidden = !meta?.auth_required || Boolean(getToken());
}

$("auth-gate")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  setToken($("auth-token").value.trim());
  $("auth-gate").hidden = true;
  state.errors.clear();
  refresh();
});

window.addEventListener("mailroom:auth-required", () => {
  const gate = $("auth-gate");
  if (gate) gate.hidden = false;
});

/* --------------------------------------------------------------- actions */

$("demo-btn").addEventListener("click", async (ev) => {
  const button = ev.currentTarget;
  switchTab("floor");
  const result = await runAction(button, null, () => postJSON("/v1/demo", { sample: "all", matter_id: "DEMO" }),
    (res) => `Dropped ${res?.started?.length ?? 0} sample filings`);
  if (result) {
    toast(`Dropped ${result.started?.length ?? 0} sample filings on the floor`);
    appendLog({ type: "demo", subject: `dropped ${result.started?.length ?? 0} sample filings` });
    refresh();
  }
});

$("brief-btn").addEventListener("click", () => {
  switchTab("topics");
  $("topic-subject")?.focus();
});

async function doUpload(input, statusEl, trigger) {
  const file = input.files?.[0];
  if (!file) return;
  const matter = $("inbox-matter")?.value || "UPLOAD";
  const result = await runAction(trigger, statusEl, () => uploadFile(file, matter), (res) => `Queued ${res.file} (${res.doc_id})`);
  input.value = "";
  if (result) {
    toast(`Queued ${result.file} for the floor`);
    refresh();
  }
}

// Real buttons open the hidden pickers (a label around a hidden input was
// not keyboard reachable).
$("upload-btn").addEventListener("click", () => $("upload").click());
$("upload").addEventListener("change", (ev) => doUpload(ev.target, null, $("upload-btn")));
$("inbox-upload-btn")?.addEventListener("click", () => $("inbox-upload").click());
$("inbox-upload")?.addEventListener("change", (ev) => doUpload(ev.target, $("inbox-status"), $("inbox-upload-btn")));

$("dataset-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const button = ev.submitter || ev.target.querySelector("button[type=submit]");
  const corpus = $("dataset-corpus").value;
  const limit = Math.max(1, Math.min(25, Number($("dataset-limit").value || 3)));
  const matterId = $("dataset-matter").value || "HUB";
  const result = await runAction(button, $("dataset-status"), () => postJSON("/v1/datasets/pull", { corpus, limit, matter_id: matterId }),
    (res) => `Queued ${res.started?.length ?? 0} of ${res.requested ?? limit} rows from ${corpus}`);
  if (result) refresh();
});

$("lookup-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = $("lookup-q").value.trim();
  const hits = $("lookup-hits");
  if (q.length < 2) {
    hits.innerHTML = emptyState("Type at least two characters.");
    return;
  }
  try {
    const payload = await getJSON(`/v1/search?q=${encodeURIComponent(q)}`);
    renderLookup(payload.documents || []);
    announce(`${(payload.documents || []).length} filings match ${q}`);
  } catch (err) {
    hits.innerHTML = errorState(errText(err));
  }
});

$("topic-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const action = ev.submitter?.dataset.action || "launch";
  const subject = $("topic-subject").value.trim();
  if (!subject) return;
  const ingestEl = $("topic-ingest");
  const result = await runAction(ev.submitter, $("topic-status"), () => postJSON("/v1/topics", {
    subject,
    body: $("topic-body").value,
    matter_id: $("topic-matter").value || "DEFAULT",
    route_to: $("topic-route").value,
    action,
    // Unchecked means "let the office guess", not "never file".
    ingest: ingestEl?.checked ? true : null,
  }), (res) => (action === "queue" ? `Queued “${subject}”` : `Launched “${subject}” to ${res?.topic?.route_to || "the floor"}`));
  if (result) {
    $("topic-subject").value = "";
    $("topic-body").value = "";
    refresh();
  }
});

$("sweep-btn").addEventListener("click", async (ev) => {
  const result = await runAction(ev.currentTarget, $("ops-note"), () => postJSON("/v1/ops/sweep", {}),
    (res) => `Sweep: ${res.escalated || 0} hive pings · review ${res.review || 0} · returns ${res.failed || 0} · reconsider ${res.reconsider || 0}`);
  if (result) {
    renderOpsResults(result, "sweep");
    refresh();
  }
});

$("recover-btn").addEventListener("click", async (ev) => {
  const result = await runAction(ev.currentTarget, $("ops-note"), () => postJSON("/v1/ops/recover", {}),
    (res) => (res.count ? `Requeued ${res.count} stuck filing${res.count === 1 ? "" : "s"} to the inbox` : "Nothing stuck to recover"));
  if (result) {
    renderOpsResults(result, "recover");
    refresh();
  }
});

$("archive-reconsider-only")?.addEventListener("change", (ev) => {
  state.archiveReconsiderOnly = ev.target.checked;
  refreshPanel("archive");
});

window.addEventListener("mailroom:inspect", (ev) => {
  const docId = ev.detail?.doc_id;
  if (!docId) return;
  switchTab("floor");
  showInspect({ doc_id: docId, filename: docId });
});

/* ------------------------------------------------------------------ boot */

function wireCredits() {
  $("limezu-credit")?.addEventListener("click", (ev) => {
    if (window.mailroomDesktop?.openCredits) {
      ev.preventDefault();
      window.mailroomDesktop.openCredits();
    }
  });
}

function markTheme() {
  const lamp = $("theme-lamp");
  if (!lamp) return;
  const theme = floor.themeSource || window.__MAILROOM__?.theme || "procedural";
  lamp.textContent = theme === "limezu" ? "Floor: LimeZu" : "Floor: procedural";
}

wireTabs();
wireCredits();
document.body.dataset.panel = "floor";
connectWS(
  (event) => {
    floor.ingestEvent(event);
    appendLog(event);
  },
  (wsState) => {
    if (wsState === "closed") appendLog({ type: "ws", subject: "live stream disconnected, retrying" });
  },
);

// One boot refresh (the old code refreshed twice at startup) then the poll.
const whenBooted = floor.booted && typeof floor.booted.then === "function" ? floor.booted : Promise.resolve();
whenBooted
  .catch((err) => console.warn("office boot", err))
  .finally(() => {
    markTheme();
    refresh();
    setInterval(refresh, 2500);
  });
