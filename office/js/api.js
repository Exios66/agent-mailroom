function readToken() {
  try {
    return (
      window.localStorage.getItem("MAILROOM_TOKEN") ||
      new URLSearchParams(window.location.search).get("token") ||
      ""
    );
  } catch {
    return new URLSearchParams(window.location.search).get("token") || "";
  }
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token = readToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function getToken() {
  return readToken();
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem("MAILROOM_TOKEN", token);
    else window.localStorage.removeItem("MAILROOM_TOKEN");
  } catch {
    /* storage blocked: the token only lives for this page */
  }
}

/** Error carrying the HTTP status and the server's ``detail`` text. */
export class ApiError extends Error {
  constructor(path, status, detail) {
    super(detail || `${path} failed (${status})`);
    this.path = path;
    this.status = status;
    this.detail = detail;
  }
}

async function handleResponse(path, res) {
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("mailroom:auth-required", { detail: { path } }));
  }
  if (!res.ok) {
    let detail = "";
    try {
      const text = await res.text();
      try {
        const body = JSON.parse(text);
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
      } catch {
        detail = text.slice(0, 300);
      }
    } catch {
      detail = "";
    }
    throw new ApiError(path, res.status, detail || `${path} failed (${res.status})`);
  }
  return res.json();
}

export async function getJSON(path) {
  const res = await fetch(path, { headers: authHeaders() });
  return handleResponse(path, res);
}

export async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body || {}),
  });
  return handleResponse(path, res);
}

export async function uploadFile(file, matterId = "DEFAULT") {
  const data = new FormData();
  data.append("file", file);
  data.append("matter_id", matterId);
  const res = await fetch("/v1/upload", { method: "POST", headers: authHeaders(), body: data });
  return handleResponse("/v1/upload", res);
}

export function connectWS(onEvent, onState = () => {}) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  const ws = new WebSocket(`${proto}://${location.host}/ws${qs}`);
  ws.onopen = () => onState("open");
  ws.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {
      /* ignore malformed frames */
    }
  };
  ws.onclose = () => {
    onState("closed");
    setTimeout(() => connectWS(onEvent, onState), 2000);
  };
  return ws;
}
