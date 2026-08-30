import { OfficeFloor, DESKS } from "./floor.js";
import { CAST, ROSTER_CAST } from "./cast.js";
import { connectWS, getJSON, postJSON, uploadFile } from "./api.js";

const inspect = document.getElementById("inspect");
const reviewList = document.getElementById("review-list");
const hiveList = document.getElementById("hive-list");
const metricsEl = document.getElementById("metrics");
const consoleLog = document.getElementById("console-log");
const counts = document.getElementById("counts");
const providerEl = document.getElementById("provider");

const floor = new OfficeFloor(document.getElementById("floor"), showInspect);
const logLines = [];

function showInspect(item) {
  if (!item) {
    inspect.innerHTML = `<p class="muted">Nothing selected.</p>`;
    return;
  }
  const title = item.filename || item.agent || "Selection";
  const chips = [
    item.stage && `<span class="chip">${item.stage}</span>`,
    item.doc_type && `<span class="chip">${item.doc_type}</span>`,
    item.needs_human && `<span class="chip review">needs human</span>`,
    item.agent && `<span class="chip">${item.agent}</span>`,
  ].filter(Boolean).join("");
  const fields = item.extracted_data
    ? `<pre>${escapeHtml(JSON.stringify(item.extracted_data, null, 2))}</pre>`
    : "";
  inspect.innerHTML = `
    <div class="card">
      <h3>${escapeHtml(title)}</h3>
      <div>${chips}</div>
      <p class="muted">${escapeHtml(item.doc_id || item.desk || "")}</p>
      ${item.thought ? `<p>${escapeHtml(item.thought)}</p>` : ""}
      ${item.escalation_reason ? `<p>${escapeHtml(item.escalation_reason)}</p>` : ""}
      ${item.report ? `<p>${escapeHtml(item.report)}</p>` : ""}
      ${fields}
    </div>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function switchTab(name) {
  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  document.getElementById("panel-title").textContent = {
    floor: "Command Center",
    topics: "Live Topics",
    review: "Review Siding",
    hive: "Hive Mailboxes",
    metrics: "Branch Metrics",
    console: "Live Console",
  }[name];
}

document.getElementById("tabs").addEventListener("click", (ev) => {
  const btn = ev.target.closest("button");
  if (btn) switchTab(btn.dataset.tab);
});

document.getElementById("demo-btn").addEventListener("click", async () => {
  await postJSON("/v1/demo", { sample: "all", matter_id: "SCRANTON" });
});

document.getElementById("brief-btn").addEventListener("click", () => switchTab("topics"));

document.getElementById("topic-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const action = ev.submitter?.dataset.action || "launch";
  const subject = document.getElementById("topic-subject").value.trim();
  const body = document.getElementById("topic-body").value;
  const matterId = document.getElementById("topic-matter").value || "DEFAULT";
  const routeTo = document.getElementById("topic-route").value;
  if (!subject) return;
  await postJSON("/v1/topics", { subject, body, matter_id: matterId, route_to: routeTo, action });
  document.getElementById("topic-subject").value = "";
  document.getElementById("topic-body").value = "";
  refresh();
});

document.getElementById("upload").addEventListener("change", async (ev) => {
  const file = ev.target.files?.[0];
  if (file) await uploadFile(file, "UPLOAD");
  ev.target.value = "";
});

function appendLog(event) {
  const line = `${event.type.padEnd(8)} ${event.stage || event.act || ""} ${event.filename || event.subject || event.doc_id || ""}`;
  logLines.push(line);
  consoleLog.textContent = logLines.slice(-80).join("\n");
}

function renderReview(docs) {
  if (!docs.length) {
    reviewList.innerHTML = `<p class="muted">No documents on the siding. The floor is clearing itself.</p>`;
    return;
  }
  reviewList.innerHTML = docs.map((doc) => `
    <div class="card" data-doc="${doc.doc_id}">
      <h3>${escapeHtml(doc.original_filename)}</h3>
      <span class="chip review">${escapeHtml(doc.doc_type || "unknown")}</span>
      <p class="muted">${escapeHtml(doc.escalation_reason || "needs a human")}</p>
      <label>Doc type
        <select class="dtype">
          ${["contract","merger_agreement","corporate_record","correspondence","compliance_filing","insurance_claim"].map((t) =>
            `<option ${t === doc.doc_type ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </label>
      <label>Notes <input class="notes" placeholder="that's what she said"></label>
      <div class="row">
        <button data-act="approved" data-disp="resume">Approve</button>
        <button data-act="rejected" data-disp="resume">Reject</button>
        <button data-act="approved" data-disp="requeue">Requeue</button>
      </div>
    </div>`).join("");
  reviewList.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const card = btn.closest(".card");
      await postJSON(`/v1/review/${card.dataset.doc}/resolve`, {
        decision: btn.dataset.act,
        disposition: btn.dataset.disp,
        doc_type: card.querySelector(".dtype").value,
        notes: card.querySelector(".notes").value,
      });
      refresh();
    });
  });
}

function renderHive(data) {
  const cards = Object.entries(data.registry || {}).map(([name, meta]) => {
    const character = ROSTER_CAST[name];
    const mail = (data.inboxes?.[name] || []).slice(0, 3);
    return `<div class="card">
      <h3>${escapeHtml(CAST[character]?.name || name)} · ${escapeHtml(meta.role)}</h3>
      <p class="muted">${escapeHtml(name)} · inbox ${meta.inbox_count || 0}</p>
      ${mail.map((m) => `<div class="chip">${escapeHtml(m.act)} ${escapeHtml(m.subject)}</div>`).join("")}
    </div>`;
  });
  hiveList.innerHTML = cards.join("");
}

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

function renderMetrics(runs, health, ops) {
  const stages = {};
  for (const run of runs) stages[run.stage] = (stages[run.stage] || 0) + 1;
  providerEl.textContent = health?.checks?.llm_provider || "mock";
  const lamp = health?.checks?.watcher || ops?.watcher?.lamp || "ok";
  const pending = health?.checks?.inbox_pending ?? ops?.inbox_pending ?? 0;
  document.getElementById("lamp").textContent =
    lamp === "ok" ? "SOURCE: LIVE PIPELINE" : `SOURCE: WATCHER ${String(lamp).toUpperCase()}`;
  metricsEl.innerHTML = `
    <div class="card"><h3>On the floor</h3><p>${runs.length} documents</p></div>
    <div class="card"><h3>Watcher</h3><p>${escapeHtml(lamp)} · inbox ${pending}</p></div>
    <div class="card"><h3>Review siding</h3><p>${ops?.review_queue ?? 0}</p></div>
    ${Object.entries(stages).map(([k, v]) => `<div class="card"><h3>${escapeHtml(k)}</h3><p>${v}</p></div>`).join("")}
  `;
}

async function refresh() {
  try {
    const [floorData, review, hive, health, topics, ops] = await Promise.all([
      getJSON("/v1/floor"),
      getJSON("/v1/review/queue"),
      getJSON("/v1/hive"),
      getJSON("/v1/health"),
      getJSON("/v1/topics"),
      getJSON("/v1/ops/status"),
    ]);
    floor.applySnapshot(floorData.runs || []);
    renderReview(review.documents || []);
    renderHive(hive);
    renderTopics(topics.topics || []);
    renderMetrics(floorData.runs || [], health, ops);
    const queued = topics.queued || 0;
    const live = topics.live || 0;
    counts.textContent = `${floorData.runs?.length || 0} docs · ${live} live topics · ${queued} queued`;
  } catch (err) {
    appendLog({ type: "error", subject: String(err) });
  }
}

connectWS((event) => {
  floor.ingestEvent(event);
  appendLog(event);
});

refresh();
setInterval(refresh, 2500);

void DESKS;
