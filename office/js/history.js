import { getJSON } from "./api.js?v=mailroom8";

export const HistoryView = (() => {
  const listEl = () => document.getElementById("history-list");
  const refreshBtn = () => document.getElementById("history-refresh");

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function chip(run) {
    const stage = run.stage || "unknown";
    return `<span class="chip">${esc(stage.toUpperCase())}</span>`;
  }

  function renderHistory(runs) {
    const el = listEl();
    if (!el) return;
    if (!runs.length) {
      el.innerHTML = `<p class="muted">No runs in the recent window.</p>`;
      return;
    }
    el.innerHTML = runs.map((run) => {
      const id = run.trace_id || run.doc_id;
      const when = run.updated_at || run.created_at || "";
      return `<div class="card run-row" data-trace="${esc(id)}">
        <h3>${esc(run.filename || id)}</h3>
        ${chip(run)}
        <span class="chip">${esc(run.doc_type || "—")}</span>
        <p class="muted">${esc(when)}</p>
        <div class="row">
          <button class="action history-replay" data-trace="${esc(id)}">Replay</button>
          <button class="action history-inspect" data-trace="${esc(id)}">Inspect</button>
        </div>
      </div>`;
    }).join("");
    for (const btn of el.querySelectorAll(".history-replay")) {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        await replayRun(btn.dataset.trace);
      });
    }
    for (const btn of el.querySelectorAll(".history-inspect")) {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        window.dispatchEvent(new CustomEvent("mailroom:inspect", { detail: { doc_id: btn.dataset.trace } }));
      });
    }
  }

  async function replayRun(traceId) {
    const data = await getJSON(`/v1/runs/${encodeURIComponent(traceId)}`);
    const floor = window.__MAILROOM_FLOOR__;
    if (floor?.replay) floor.replay(data);
    document.querySelector('.tabs button[data-tab="floor"]')?.click();
  }

  async function refresh() {
    const el = listEl();
    if (!el) return null;
    el.innerHTML = `<p class="muted">Loading run history…</p>`;
    const data = await getJSON("/v1/history");
    renderHistory(data.runs || []);
    return data;
  }

  const btn = refreshBtn();
  if (btn) {
    btn.addEventListener("click", () => refresh().catch(() => {}));
  }

  return { refresh, replayRun };
})();
