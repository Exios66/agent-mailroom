function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token =
    window.localStorage.getItem("MAILROOM_TOKEN") ||
    new URLSearchParams(window.location.search).get("token") ||
    "";
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export async function getJSON(path) {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

export async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadFile(file, matterId = "DEFAULT") {
  const data = new FormData();
  data.append("file", file);
  data.append("matter_id", matterId);
  const res = await fetch("/v1/upload", { method: "POST", headers: authHeaders(), body: data });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function connectWS(onEvent) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
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
