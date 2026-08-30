import { OfficeFloor } from "./floor.js?v=mailroom8";
import { CAST, ROSTER_CAST } from "./cast.js?v=mailroom8";
import { connectWS, getJSON, getToken, postJSON, setToken, uploadFile } from "./api.js?v=mailroom8";
import { HistoryView } from "./history.js?v=mailroom8";

const inspect = document.getElementById("inspect");
const reviewList = document.getElementById("review-list");
const hiveList = document.getElementById("hive-list");
const metricsEl = document.getElementById("metrics");
const providersPanel = document.getElementById("providers-panel");
const opsResults = document.getElementById("ops-results");
const consoleLog = document.getElementById("console-log");
const counts = document.getElementById("counts");
const providerEl = document.getElementById("provider");

const floor = new OfficeFloor(document.getElementById("floor"), (item) => {
  if (item?.tray && item.tab) switchTab(item.tab);
  else switchTab("floor");
  showInspect(item);
});
window.__MAILROOM_FLOOR__ = floor;
const logLines = [];

function showInspect(item) {
  if (!item) {
    inspect.innerHTML = `<p class="muted">Nothing selected.</p>`;
    return;
  }
  renderInspectCard(item);
  if (item.doc_id) {
    getJSON(`/v1/inspect/${item.doc_id}`).then((payload) => {
      renderInspectCard({
        ...item,
        ...payload.document,
        _audit: payload.audit,
        _source: payload.source,
        _conflict: payload.conflict,
        _spans: payload.spans,
      });
    }).catch(() => {});
  }
}

function renderInspectCard(item) {
  const title = item.filename || item.original_filename || item.agent || "Selection";
  const pile = (item.documents || []).map((row) =>
    `<p><button class="linkish" data-doc="${escapeHtml(row.doc_id)}">${escapeHtml(row.filename || row.original_filename || row.doc_id)}</button> <span class="chip">${escapeHtml(row.stage || row.bin || "")}</span></p>`
  ).join("");
  const chips = [
    item.tray && `<span class="chip">${item.tray} tray</span>`,
    item.stage && `<span class="chip">${item.stage}</span>`,
    item.bin && `<span class="chip">${item.bin}</span>`,
    item.doc_type && `<span class="chip">${item.doc_type}</span>`,
    item.doc_subclass && `<span class="chip">${item.doc_subclass}</span>`,
    item.needs_reconsideration && `<span class="chip review">RECONSIDER</span>`,
    item.conflict_detected && `<span class="chip fail">conflict</span>`,
    item.needs_human && `<span class="chip review">needs human</span>`,
    item.agent && `<span class="chip">${item.agent}</span>`,
  ].filter(Boolean).join("");
  const causes = (item.review_causes || []).map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("");
  const path = (item.routing_path || []).join(" → ");
  const fields = item.extracted_data
    ? `<pre>${escapeHtml(JSON.stringify(item.extracted_data, null, 2))}</pre>`
    : "";
  const spans = (item._spans || []).map((span) =>
    `<li><b>${escapeHtml(span.name)}</b> ${Number(span.latency_ms || 0).toFixed(0)}ms</li>`
  ).join("");
  const spanBlock = spans ? `<details class="card"><summary>Trace spans</summary><ol class="audit">${spans}</ol></details>` : "";
  const audit = item._audit
    ? `<p class="muted">Audit ${item._audit.chain_valid ? "valid" : "BROKEN"} · ${item._audit.chain_length} links</p>
       <ol class="audit">${(item._audit.entries || []).slice(-8).map((e) =>
         `<li><b>${escapeHtml(e.event)}</b> ${escapeHtml(e.actor)} <span class="muted">${escapeHtml(e.timestamp || "")}</span></li>`
       ).join("")}</ol>`
    : "";
  const source = item._source
    ? `<details class="card" open><summary>Source · ${escapeHtml(item._source.bin || "")}</summary><pre>${escapeHtml(item._source.text || "")}</pre></details>`
    : "";
  const conflict = item._conflict
    ? `<p class="fail-text">${escapeHtml(item._conflict.reason || "matter conflict")}</p>`
    : "";
  inspect.innerHTML = `
    <div class="card">
      <h3>${escapeHtml(title)}</h3>
      <div>${chips}${causes}</div>
      <p class="muted">${escapeHtml(item.doc_id || item.desk || "")} · ${escapeHtml(item.matter_id || "")}</p>
      ${item.classification_confidence != null ? `<p class="muted">classify ${(item.classification_confidence * 100).toFixed(0)}% · extract ${item.extraction_confidence != null ? (item.extraction_confidence * 100).toFixed(0) + "%" : "—"}</p>` : ""}
      ${path ? `<p class="muted">${escapeHtml(path)}</p>` : ""}
      ${item.thought ? `<p>${escapeHtml(item.thought)}</p>` : ""}
      ${item.escalation_reason ? `<p>${escapeHtml(item.escalation_reason)}</p>` : ""}
      ${conflict}
      ${item.report ? `<p>${escapeHtml(item.report)}</p>` : ""}
      ${fields}
      ${spanBlock}
      ${audit}
      ${source}
      ${pile ? `<div class="tray-pile">${pile}</div>` : ""}
    </div>
    ${reviewActionsHtml(item)}`;
  wireReviewActions(inspect, item);
  inspect.querySelectorAll("[data-doc]").forEach((link) => {
    link.addEventListener("click", () => {
      switchTab("floor");
      showInspect({ doc_id: link.dataset.doc, filename: link.textContent });
    });
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function switchTab(name) {
  document.querySelectorAll(".tabs button[data-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  document.body.dataset.panel = name;
  document.getElementById("panel-title").textContent = {
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
  }[name];
}

function wireTabs() {
  document.querySelectorAll(".tabs button[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
      if (btn.dataset.tab === "history") HistoryView.refresh().catch(() => {});
    });
  });
}

wireTabs();

window.addEventListener("mailroom:inspect", (ev) => {
  const docId = ev.detail?.doc_id;
  if (!docId) return;
  switchTab("floor");
  showInspect({ doc_id: docId, filename: docId });
});

document.getElementById("demo-btn").addEventListener("click", async () => {
  switchTab("floor");
  try {
    const result = await postJSON("/v1/demo", { sample: "all", matter_id: "DEMO" });
    const n = result?.started?.length ?? 0;
    appendLog({ type: "demo", subject: `dropped ${n} sample filings` });
    await refresh();
  } catch (err) {
    appendLog({ type: "error", subject: String(err) });
  }
});

document.getElementById("dataset-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const corpus = document.getElementById("dataset-corpus").value;
  const limit = Number(document.getElementById("dataset-limit").value || 3);
  const matterId = document.getElementById("dataset-matter").value || "HUB";
  await postJSON("/v1/datasets/pull", { corpus, limit, matter_id: matterId });
  refresh();
});

document.getElementById("lookup-form")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = document.getElementById("lookup-q").value.trim();
  const hits = document.getElementById("lookup-hits");
  if (q.length < 2) {
    hits.innerHTML = `<p class="muted">Type at least two characters.</p>`;
    return;
  }
  try {
    const payload = await getJSON(`/v1/search?q=${encodeURIComponent(q)}`);
    renderLookup(payload.documents || []);
  } catch (err) {
    hits.innerHTML = `<p class="muted">${escapeHtml(String(err))}</p>`;
  }
});

document.getElementById("brief-btn").addEventListener("click", () => switchTab("topics"));

document.getElementById("topic-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const action = ev.submitter?.dataset.action || "launch";
  const subject = document.getElementById("topic-subject").value.trim();
  const body = document.getElementById("topic-body").value;
  const matterId = document.getElementById("topic-matter").value || "DEFAULT";
  const routeTo = document.getElementById("topic-route").value;
  const ingestEl = document.getElementById("topic-ingest");
  const ingest = ingestEl?.checked ? true : ingestEl && !ingestEl.checked ? false : null;
  if (!subject) return;
  await postJSON("/v1/topics", { subject, body, matter_id: matterId, route_to: routeTo, action, ingest });
  document.getElementById("topic-subject").value = "";
  document.getElementById("topic-body").value = "";
  refresh();
});

document.getElementById("upload").addEventListener("change", async (ev) => {
  const file = ev.target.files?.[0];
  const matter = document.getElementById("inbox-matter")?.value || "UPLOAD";
  if (file) await uploadFile(file, matter);
  ev.target.value = "";
  refresh();
});

document.getElementById("inbox-upload")?.addEventListener("change", async (ev) => {
  const file = ev.target.files?.[0];
  const matter = document.getElementById("inbox-matter")?.value || "UPLOAD";
  if (file) await uploadFile(file, matter);
  ev.target.value = "";
  refresh();
});

function appendLog(event) {
  const line = `${event.type.padEnd(8)} ${event.stage || event.act || ""} ${event.filename || event.subject || event.doc_id || ""}`;
  logLines.push(line);
  consoleLog.textContent = logLines.slice(-80).join("\n");
}

let DOC_CLASSES = ["contract", "merger_agreement", "corporate_record", "correspondence", "compliance_filing", "insurance_claim"];
let SUBCLASS_CATALOG = {};
let archiveReconsiderOnly = false;

function subclassOptionsHtml(docType, value = "") {
  const options = SUBCLASS_CATALOG[docType] || [];
  const opts = options.map((s) =>
    `<option value="${escapeHtml(s)}"${s === value ? " selected" : ""}>${escapeHtml(s)}</option>`
  ).join("");
  return `<datalist id="subclass-${escapeHtml(docType)}">${opts}</datalist>`;
}

function reviewActionsHtml(doc) {
  if (doc.stage !== "review" && !doc.needs_human) return "";
  const dtype = doc.doc_type || "contract";
  return `
    <div class="card review-actions" data-doc="${escapeHtml(doc.doc_id)}">
      <h3>Resolve from inspector</h3>
      <label>Doc type
        <select class="dtype">
          ${DOC_CLASSES.map((t) => `<option ${t === dtype ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </label>
      ${subclassOptionsHtml(dtype, doc.doc_subclass || "")}
      <label>Subclass <input class="subclass" list="subclass-${escapeHtml(dtype)}" value="${escapeHtml(doc.doc_subclass || "")}" placeholder="pick or type"></label>
      <label>Notes <input class="notes" placeholder="operator notes"></label>
      <label>Extracted JSON <textarea class="extracted" rows="4">${escapeHtml(JSON.stringify(doc.extracted_data || {}, null, 2))}</textarea></label>
      <div class="row">
        <button type="button" data-act="approved" data-disp="resume">Approve</button>
        <button type="button" data-act="approved" data-disp="record">Record</button>
        <button type="button" data-act="approved" data-disp="complete">Complete</button>
        <button type="button" data-act="rejected" data-disp="complete">Reject</button>
        <button type="button" data-act="approved" data-disp="requeue">Requeue</button>
      </div>
    </div>`;
}

function wireReviewActions(root, doc) {
  const card = root.querySelector(".review-actions") || root;
  if (!card?.dataset?.doc && !doc?.doc_id) return;
  const docId = card.dataset.doc || doc.doc_id;
  card.querySelectorAll("button[data-act]").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      let extracted = null;
      try { extracted = JSON.parse(card.querySelector(".extracted")?.value || "{}"); } catch { extracted = null; }
      await postJSON(`/v1/review/${docId}/resolve`, {
        decision: btn.dataset.act,
        disposition: btn.dataset.disp,
        doc_type: card.querySelector(".dtype")?.value,
        doc_subclass: card.querySelector(".subclass")?.value,
        notes: card.querySelector(".notes")?.value,
        extracted_data: extracted,
      });
      refresh();
    });
  });
  const dtypeSel = card.querySelector(".dtype");
  const subclassInput = card.querySelector(".subclass");
  if (dtypeSel && subclassInput) {
    dtypeSel.addEventListener("change", () => {
      const listId = `subclass-${dtypeSel.value}`;
      subclassInput.setAttribute("list", listId);
      if (!document.getElementById(listId) && SUBCLASS_CATALOG[dtypeSel.value]) {
        const dl = document.createElement("datalist");
        dl.id = listId;
        dl.innerHTML = SUBCLASS_CATALOG[dtypeSel.value].map((s) => `<option value="${escapeHtml(s)}">`).join("");
        card.appendChild(dl);
      }
    });
  }
}

function renderReview(docs) {
  if (!docs.length) {
    reviewList.innerHTML = `<p class="muted">No documents on the siding. The floor is clearing itself.</p>`;
    return;
  }
  reviewList.innerHTML = docs.map((doc) => {
    const dtype = doc.doc_type || "contract";
    return `
    <div class="card" data-doc="${doc.doc_id}" data-stage="review">
      <h3>${escapeHtml(doc.original_filename)}</h3>
      <span class="chip review">${escapeHtml(doc.doc_type || "unknown")}</span>
      ${(doc.review_causes || []).map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")}
      <p class="muted">${escapeHtml(doc.escalation_reason || "needs a human")}</p>
      <p class="muted">${escapeHtml(doc.matter_id || "")} · bin ${escapeHtml(doc.bin || "review")}</p>
      ${reviewActionsHtml({ ...doc, stage: "review" })}
      <details><summary>Read source</summary><pre class="source-pane" data-src="${doc.doc_id}">loading…</pre></details>
    </div>`;
  }).join("");
  docs.forEach((doc) => {
    const card = reviewList.querySelector(`.card[data-doc="${doc.doc_id}"]`);
    if (card) wireReviewActions(card, doc);
  });
  reviewList.querySelectorAll("details").forEach((el) => {
    el.addEventListener("toggle", async (ev) => {
      ev.stopPropagation();
      if (!el.open) return;
      const pane = el.querySelector(".source-pane");
      if (!pane || pane.dataset.ready) return;
      try {
        const src = await getJSON(`/v1/documents/${pane.dataset.src}/source`);
        pane.textContent = src.text || "";
        pane.dataset.ready = "1";
      } catch (err) {
        pane.textContent = String(err);
      }
    });
  });
  bindInspectCards(reviewList);
}

function bindInspectCards(root) {
  root.querySelectorAll(".card[data-doc]").forEach((card) => {
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button,input,select,textarea,label,details,a,.review-actions")) return;
      const id = card.dataset.doc;
      if (!id) return;
      switchTab("floor");
      showInspect({ doc_id: id, filename: card.querySelector("h3")?.textContent || id, stage: card.dataset.stage });
    });
  });
}

function renderLookup(docs) {
  const hits = document.getElementById("lookup-hits");
  if (!hits) return;
  if (!docs.length) {
    hits.innerHTML = `<p class="muted">No filings match.</p>`;
    return;
  }
  hits.innerHTML = docs.map((doc) => `
    <div class="card" data-doc="${doc.doc_id}">
      <h3>${escapeHtml(doc.original_filename)}</h3>
      <span class="chip">${escapeHtml(doc.stage)}</span>
      <span class="chip">${escapeHtml(doc.doc_type || "unknown")}</span>
      <p class="muted">${escapeHtml(doc.matter_id)} · ${escapeHtml(doc.doc_id)}</p>
    </div>`).join("");
  bindInspectCards(hits);
}

function renderInbox(queue, classified) {
  const list = document.getElementById("inbox-list");
  if (!list) return;
  const hopper = queue.inbox || queue.queued || [];
  const processing = queue.processing || [];
  const snaps = classified || [];
  if (!hopper.length && !processing.length && !snaps.length) {
    list.innerHTML = `<p class="muted">Hopper is empty. Upload a filing or drop a pile.</p>`;
    return;
  }
  list.innerHTML = [
    ...hopper.map((row) => `
      <div class="card" data-doc="${escapeHtml(row.doc_id || "")}">
        <h3>${escapeHtml(row.filename)}</h3>
        <span class="chip">inbox</span>
        <p class="muted">${escapeHtml(row.matter_id || "")} · ${escapeHtml(row.source || "")}</p>
      </div>`),
    ...processing.map((row) => `
      <div class="card" data-doc="${escapeHtml(row.doc_id || "")}">
        <h3>${escapeHtml(row.original_filename || row.filename)}</h3>
        <span class="chip">${escapeHtml(row.stage || "processing")}</span>
        <p class="muted">${escapeHtml(row.matter_id || "")} · ${escapeHtml(row.bin || "")}</p>
      </div>`),
    ...snaps.slice(0, 8).map((row) => `
      <div class="card" data-doc="${escapeHtml(row.doc_id || "")}">
        <h3>${escapeHtml(row.original_filename || row.filename)}</h3>
        <span class="chip">classified</span>
        <p class="muted">${escapeHtml(row.doc_type || row.classified_type || "")} snapshot</p>
      </div>`),
  ].join("");
  bindInspectCards(list);
}

function renderArchive(docs) {
  const list = document.getElementById("archive-list");
  if (!list) return;
  if (!docs.length) {
    list.innerHTML = `<p class="muted">${archiveReconsiderOnly ? "No reconsider filings on the shelves." : "Creed's shelves are empty."}</p>`;
    return;
  }
  list.innerHTML = docs.map((doc) => `
    <div class="card" data-doc="${doc.doc_id}" data-stage="${escapeHtml(doc.stage || "archived")}">
      <h3>${escapeHtml(doc.original_filename)}</h3>
      <span class="chip">${escapeHtml(doc.doc_type || "unknown")}</span>
      ${doc.needs_reconsideration ? `<span class="chip review">RECONSIDER</span>` : `<span class="chip">chain ${doc.bin || "archive"}</span>`}
      ${(doc.review_causes || []).map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")}
      <p class="muted">${escapeHtml(doc.matter_id)} · ${escapeHtml(doc.doc_id)}</p>
      <div class="row">
        ${doc.needs_reconsideration ? `<button type="button" data-requeue="${doc.doc_id}">Requeue</button>` : ""}
        <button type="button" data-verify="${doc.doc_id}">Verify chain</button>
      </div>
      <pre class="verify-pane" hidden></pre>
    </div>`).join("");
  bindInspectCards(list);
  list.querySelectorAll("[data-requeue]").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const result = await postJSON(`/v1/archive/${btn.dataset.requeue}/requeue`, {});
      window.__MAILROOM_OPS_NOTE__ = `Requeued ${btn.dataset.requeue} → ${result.doc_id}`;
      refresh();
    });
  });
  list.querySelectorAll("[data-verify]").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const card = btn.closest(".card");
      const pane = card.querySelector(".verify-pane");
      const result = await getJSON(`/v1/archive/${btn.dataset.verify}/verify`);
      pane.hidden = false;
      pane.textContent = result.chain_valid
        ? `VALID · ${result.chain_length} links`
        : `BROKEN · ${result.chain_length} links`;
    });
  });
}

function renderFailed(docs) {
  const list = document.getElementById("failed-list");
  if (!list) return;
  if (!docs.length) {
    list.innerHTML = `<p class="muted">No returns. Rejected filings land here.</p>`;
    return;
  }
  list.innerHTML = docs.map((doc) => `
    <div class="card" data-doc="${doc.doc_id}" data-stage="failed">
      <h3>${escapeHtml(doc.original_filename)}</h3>
      <span class="chip fail">failed</span>
      ${(doc.review_causes || []).map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")}
      <p class="muted">${escapeHtml(doc.escalation_reason || "rejected")}</p>
    </div>`).join("");
  bindInspectCards(list);
}

function renderMatters(data) {
  const list = document.getElementById("matter-list");
  if (!list) return;
  const rows = data.matters || [];
  if (!rows.length) {
    list.innerHTML = `<p class="muted">No matters yet. Upload or pull a corpus.</p>`;
    return;
  }
  list.innerHTML = rows.map((row) => `
    <div class="card" data-matter="${escapeHtml(row.matter_id)}">
      <h3>${escapeHtml(row.matter_id)}</h3>
      <span class="chip">${row.document_count} docs</span>
      <span class="chip review">${row.review_count || 0} review</span>
      <span class="chip">${row.archived_count || 0} archived</span>
      <div class="row"><button data-open="${escapeHtml(row.matter_id)}">Open matter</button></div>
      <div class="matter-docs" hidden></div>
    </div>`).join("");
  list.querySelectorAll("[data-open]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const card = btn.closest(".card");
      const pane = card.querySelector(".matter-docs");
      const payload = await getJSON(`/v1/matters/${encodeURIComponent(btn.dataset.open)}`);
      pane.hidden = false;
      pane.innerHTML = (payload.documents || []).map((doc) =>
        `<p><button class="linkish" data-doc="${doc.doc_id}">${escapeHtml(doc.original_filename)}</button> <span class="chip">${escapeHtml(doc.stage)}</span></p>`
      ).join("");
      pane.querySelectorAll("[data-doc]").forEach((link) => {
        link.addEventListener("click", () => {
          switchTab("floor");
          showInspect({ doc_id: link.dataset.doc, filename: link.textContent });
        });
      });
    });
  });
}

function renderHive(data) {
  const acts = floor.hiveActs || {};
  const board = data.board?.content || "";
  const boardBlock = board
    ? `<div class="card"><h3>Blackboard</h3><pre class="hive-board">${escapeHtml(board)}</pre></div>`
    : "";
  const cards = Object.entries(data.registry || {}).map(([name, meta]) => {
    const character = ROSTER_CAST[name];
    const mail = (data.inboxes?.[name] || []).slice(0, 3);
    return `<div class="card">
      <h3>${escapeHtml(CAST[character]?.name || name)} · ${escapeHtml(meta.role)}</h3>
      <p class="muted">${escapeHtml(name)} · inbox ${meta.inbox_count || 0}</p>
      ${mail.map((m) => {
        const color = acts[m.act] || "#fff8e7";
        return `<div class="chip" style="background:${color}">${escapeHtml(m.act)} ${escapeHtml(m.subject)}</div>`;
      }).join("")}
    </div>`;
  });
  hiveList.innerHTML = boardBlock + cards.join("");
}

function renderProviders(data) {
  if (!providersPanel || !data) return;
  const harnesses = data.harnesses || [];
  providerEl.textContent = data.requested !== data.active ? `${data.requested}→${data.active}` : (data.active || "mock");
  providersPanel.innerHTML = `
    <div class="card">
      <h3>LLM harnesses</h3>
      <p class="muted">Active ${escapeHtml(data.active || "")} · model ${escapeHtml(data.model || "")} · fallback ${escapeHtml(data.fallback || "")}</p>
      <table class="providers-table">
        <thead><tr><th>Agent</th><th>Provider</th><th>Model</th><th>Configured</th></tr></thead>
        <tbody>
          ${harnesses.map((row) => `
            <tr>
              <td>${escapeHtml(row.name || "")}</td>
              <td>${escapeHtml(row.name || "")}</td>
              <td>${escapeHtml(row.default_model || "")}</td>
              <td>${row.configured ? "yes" : "no"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderOpsResults(result, kind) {
  if (!opsResults || !result) return;
  if (kind === "sweep") {
    const rows = (result.details || []).map((row) =>
      `<li><button type="button" class="linkish" data-doc-link="${escapeHtml(row.doc_id)}">${escapeHtml(row.filename || row.doc_id)}</button>
        <span class="chip">${escapeHtml(row.stage || "")}</span>
        ${(row.causes || []).map((c) => `<span class="chip">${escapeHtml(c)}</span>`).join("")}
      </li>`
    ).join("");
    opsResults.innerHTML = `
      <details class="card" open>
        <summary>Sweep · ${result.escalated || 0} escalated · review ${result.review || 0} · returns ${result.failed || 0} · reconsider ${result.reconsider || 0}</summary>
        <ol class="audit">${rows || "<li class='muted'>Nothing to sweep</li>"}</ol>
      </details>`;
  } else if (kind === "recover") {
    const rows = (result.recovered || []).map((row) =>
      `<li><button type="button" class="linkish" data-doc-link="${escapeHtml(row.doc_id)}">${escapeHtml(row.doc_id)}</button>
        <span class="chip">from ${escapeHtml(row.from_bin || "?")}</span></li>`
    ).join("");
    opsResults.innerHTML = `
      <details class="card" open>
        <summary>Recover · ${result.count || 0} stuck filings moved to review</summary>
        <ol class="audit">${rows || "<li class='muted'>Nothing stuck</li>"}</ol>
      </details>`;
  }
  opsResults.querySelectorAll("[data-doc-link]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab("floor");
      showInspect({ doc_id: btn.dataset.docLink, filename: btn.textContent });
    });
  });
}

function wireAuth(meta) {
  const gate = document.getElementById("auth-gate");
  const input = document.getElementById("auth-token");
  if (!gate || !input) return;
  const required = meta?.auth_required;
  const hasToken = Boolean(getToken());
  gate.hidden = !required || hasToken;
  if (!gate.dataset.ready) {
    gate.dataset.ready = "1";
    gate.addEventListener("submit", (ev) => {
      ev.preventDefault();
      setToken(input.value.trim());
      gate.hidden = true;
      refresh();
    });
  }
}

window.addEventListener("mailroom:auth-required", () => {
  const gate = document.getElementById("auth-gate");
  if (gate) gate.hidden = false;
});

function renderTopics(topics) {
  const list = document.getElementById("topic-list");
  if (!topics.length) {
    list.innerHTML = `<p class="muted">No topics yet. Queue a brief for later or launch it onto a desk.</p>`;
    return;
  }
  list.innerHTML = topics.map((topic) => {
    const actions = topic.status === "queued"
      ? `<div class="row"><button data-launch="${topic.topic_id}">Launch</button></div>`
      : topic.status === "done"
        ? ""
        : `<div class="row"><button data-complete="${topic.topic_id}">Mark done</button></div>`;
    return `
    <div class="card">
      <h3>${escapeHtml(topic.subject)}</h3>
      <span class="chip review">${escapeHtml(topic.status)}</span>
      <span class="chip">${escapeHtml(topic.route_to)}</span>
      <p class="muted">${escapeHtml(topic.matter_id)}</p>
      ${topic.body ? `<p>${escapeHtml(topic.body).slice(0, 280)}</p>` : ""}
      ${actions}
    </div>`;
  }).join("");
  list.querySelectorAll("[data-launch]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await postJSON(`/v1/topics/${btn.dataset.launch}/launch`, {});
      refresh();
    });
  });
  list.querySelectorAll("[data-complete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await postJSON(`/v1/topics/${btn.dataset.complete}/complete`, {});
      refresh();
    });
  });
}

function renderDatasets(data) {
  const select = document.getElementById("dataset-corpus");
  const current = select.value;
  const rows = data.pipeline || [];
  if (!select.dataset.ready) {
    select.innerHTML = rows.map((c) =>
      `<option value="${escapeHtml(c.slug)}">${escapeHtml(c.slug)} · ${c.n_docs ?? "?"} rows</option>`
    ).join("");
    select.dataset.ready = "1";
    if (rows.some((c) => c.slug === "docclass-pilot")) select.value = "docclass-pilot";
  } else if (current) {
    select.value = current;
  }
  const list = document.getElementById("dataset-list");
  list.innerHTML = rows.map((c) => `
    <div class="card">
      <h3>${escapeHtml(c.slug)}</h3>
      <span class="chip">${escapeHtml(c.id)}</span>
      <p class="muted">${escapeHtml(c.note || c.role)} · ${(c.classes || []).join(", ")}</p>
    </div>`).join("");
}

function renderMetrics(runs, health, ops) {
  const stages = {};
  for (const run of runs) stages[run.stage] = (stages[run.stage] || 0) + 1;
  const llm = health?.checks?.llm || {};
  const active = llm.active || health?.checks?.llm_provider || "mock";
  const requested = llm.requested || active;
  providerEl.textContent = requested !== active ? `${requested}→${active}` : active;
  const lamp = health?.checks?.watcher || ops?.watcher?.lamp || "ok";
  const pending = health?.checks?.inbox_pending ?? ops?.inbox_pending ?? 0;
  document.getElementById("lamp").textContent =
    lamp === "ok" ? "SOURCE: LIVE PIPELINE" : `SOURCE: WATCHER ${String(lamp).toUpperCase()}`;
  const stuck = ops?.stuck_documents ?? 0;
  const reconsider = ops?.reconsider ?? 0;
  metricsEl.innerHTML = `
    <div class="card"><h3>On the floor</h3><p>${runs.length} documents</p></div>
    <div class="card"><h3>Watcher</h3><p>${escapeHtml(lamp)} · inbox ${pending}</p></div>
    <div class="card"><h3>Harness</h3><p>${escapeHtml(requested)} active ${escapeHtml(active)} · ${escapeHtml(llm.model || "")}</p></div>
    <div class="card"><h3>Review siding</h3><p>${ops?.review_queue ?? 0}</p></div>
    <div class="card"><h3>Inbox tray</h3><p>${ops?.bins?.inbox ?? 0}</p></div>
    <div class="card"><h3>Classified</h3><p>${ops?.bins?.classified ?? 0}</p></div>
    <div class="card"><h3>Returns</h3><p>${ops?.bins?.failed ?? 0}</p></div>
    <div class="card"><h3>Stuck</h3><p>${stuck}</p></div>
    <div class="card"><h3>Reconsider</h3><p>${reconsider}</p></div>
    ${Object.entries(ops?.classes || {}).map(([k, v]) => `<div class="card"><h3>${escapeHtml(k)}</h3><p>${v}</p></div>`).join("")}
    ${Object.entries(stages).map(([k, v]) => `<div class="card"><h3>${escapeHtml(k)}</h3><p>${v}</p></div>`).join("")}
    <div class="row">
      <button id="sweep-btn" class="action">Boss sweep</button>
      <button id="recover-btn" class="action">Recover stuck</button>
    </div>
    <p class="muted" id="ops-note">${escapeHtml(window.__MAILROOM_OPS_NOTE__ || "")}</p>
  `;
  document.getElementById("sweep-btn")?.addEventListener("click", async () => {
    const result = await postJSON("/v1/ops/sweep", {});
    window.__MAILROOM_OPS_NOTE__ = `Sweep: ${result.escalated || 0} hive pings · review ${result.review || 0} · returns ${result.failed || 0} · reconsider ${result.reconsider || 0}`;
    renderOpsResults(result, "sweep");
    refresh();
  });
  document.getElementById("recover-btn")?.addEventListener("click", async () => {
    const result = await postJSON("/v1/ops/recover", {});
    const names = (result.recovered || []).map((row) => row.doc_id).slice(0, 4).join(", ");
    window.__MAILROOM_OPS_NOTE__ = result.count
      ? `Recovered ${result.count}${names ? `: ${names}` : ""}`
      : "Nothing stuck to recover";
    renderOpsResults(result, "recover");
    refresh();
  });
}

function setBadge(name, count) {
  const el = document.querySelector(`[data-badge="${name}"]`);
  if (!el) return;
  const n = Number(count) || 0;
  el.textContent = String(n);
  el.hidden = n <= 0;
}

async function refresh() {
  try {
    const archivePath = archiveReconsiderOnly ? "/v1/archive?reconsider=true" : "/v1/archive";
    const [floorData, review, hive, health, topics, ops, datasets, queue, archive, failed, classified, matters, meta, consoleHist, providers] = await Promise.all([
      getJSON("/v1/floor"),
      getJSON("/v1/review/queue"),
      getJSON("/v1/hive"),
      getJSON("/v1/health"),
      getJSON("/v1/topics"),
      getJSON("/v1/ops/status"),
      getJSON("/v1/datasets"),
      getJSON("/v1/queue"),
      getJSON(archivePath),
      getJSON("/v1/failed"),
      getJSON("/v1/classified"),
      getJSON("/v1/matters"),
      getJSON("/v1/meta"),
      getJSON("/v1/console"),
      getJSON("/v1/providers").catch(() => null),
    ]);
    if (Array.isArray(meta.doc_classes) && meta.doc_classes.length) DOC_CLASSES = meta.doc_classes;
    if (meta.subclasses) SUBCLASS_CATALOG = meta.subclasses;
    wireAuth(meta);
    if (meta.hive_acts) floor.setHiveActs(meta.hive_acts);
    floor.applySnapshot(floorData.runs || [], floorData.bins);
    renderReview(review.documents || []);
    renderInbox(queue, classified.documents || []);
    renderArchive(archive.documents || []);
    renderFailed(failed.documents || []);
    renderMatters(matters);
    renderHive(hive);
    renderTopics(topics.topics || []);
    renderDatasets(datasets);
    renderMetrics(floorData.runs || [], health, ops);
    if (providers) renderProviders(providers);
    setBadge("inbox", queue.counts?.inbox ?? floorData.inbox_pending ?? 0);
    setBadge("review", review.review_queue ?? floorData.review_queue ?? 0);
    setBadge("archive", archive.count ?? floorData.archived ?? 0);
    setBadge("failed", failed.count ?? floorData.failed ?? 0);
    if (!logLines.length) {
      for (const event of (consoleHist.events || []).slice(-40)) appendLog(event);
    }
    const hopper = queue.counts?.inbox ?? floorData.inbox_pending ?? 0;
    const queued = topics.queued || 0;
    const live = topics.live || 0;
    counts.textContent = `${floorData.runs?.length || 0} docs · inbox ${hopper} · review ${floorData.review_queue || 0} · ${live} live topics · ${queued} queued`;
  } catch (err) {
    appendLog({ type: "error", subject: String(err) });
  }
}

function wireCredits() {
  const credit = document.getElementById("limezu-credit");
  if (!credit) return;
  credit.addEventListener("click", (ev) => {
    if (window.mailroomDesktop?.openCredits) {
      ev.preventDefault();
      window.mailroomDesktop.openCredits();
    }
  });
}

function markTheme() {
  const lamp = document.getElementById("theme-lamp");
  if (!lamp) return;
  const theme = floor.themeSource || window.__MAILROOM__?.theme || "procedural";
  lamp.textContent = theme === "limezu" ? "Floor: LimeZu" : "Floor: procedural";
}

wireCredits();
document.getElementById("archive-reconsider-only")?.addEventListener("change", (ev) => {
  archiveReconsiderOnly = ev.target.checked;
  refresh();
});
document.body.dataset.panel = "floor";
connectWS((event) => {
  floor.ingestEvent(event);
  appendLog(event);
});

function startOffice() {
  markTheme();
  refresh();
}
const whenBooted = floor.booted && typeof floor.booted.then === "function"
  ? floor.booted
  : Promise.resolve();
whenBooted.then(startOffice).catch((err) => {
  console.warn("office boot", err);
  startOffice();
});
refresh();
setInterval(refresh, 2500);
