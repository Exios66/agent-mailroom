function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token =
    window.localStorage.getItem("MAILROOM_TOKEN") ||
    new URLSearchParams(window.location.search).get("token") ||
    "";
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function getToken() {
  return (
    window.localStorage.getItem("MAILROOM_TOKEN") ||
    new URLSearchParams(window.location.search).get("token") ||
    ""
  );
}

export function setToken(token) {
  if (token) window.localStorage.setItem("MAILROOM_TOKEN", token);
  else window.localStorage.removeItem("MAILROOM_TOKEN");
}

async function handleResponse(path, res) {
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("mailroom:auth-required", { detail: { path } }));
    throw new Error(`${path} 401 unauthorized`);
  }
  if (!res.ok) throw new Error(`${path} ${res.status}`);
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
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("mailroom:auth-required", { detail: { path } }));
    throw new Error(`${path} 401 unauthorized`);
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadFile(file, matterId = "DEFAULT") {
  const data = new FormData();
  data.append("file", file);
  data.append("matter_id", matterId);
  const res = await fetch("/v1/upload", { method: "POST", headers: authHeaders(), body: data });
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("mailroom:auth-required"));
    throw new Error("upload 401 unauthorized");
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function connectWS(onEvent) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  const ws = new WebSocket(`${proto}://${location.host}/ws${qs}`);
  ws.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data));
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => setTimeout(() => connectWS(onEvent), 1500);
  return ws;
}
