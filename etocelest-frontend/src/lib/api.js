// Client for the ÉTOCELEST backend. No mock data anywhere: every value shown in the UI
// comes from the API (or from the SSE debate stream).

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

// Presentation metadata only (colours/icons are keyed by id in AgentTag/tailwind).
// Names and roles mirror GET /api/agents.
export const AGENTS = {
  astro: { id: "astro", name: "Astro-Weather", role: "Solar activity, radiation exposure, and launch window safety", color: "astro" },
  logistics: { id: "logistics", name: "Logistics", role: "Fuel cost, budget, and supply-chain constraints", color: "logistics" },
  crew: { id: "crew", name: "Crew Readiness", role: "Crew size, training status, and life-support margins", color: "crew" },
  missionvalue: { id: "missionvalue", name: "Mission Value", role: "Scientific return, public engagement, and trajectory visibility", color: "missionvalue" },
  judge: { id: "judge", name: "Judge", role: "Reconciles the four domains and rules on the mission plan", color: "judge" },
};

export const RESOLUTION_LABELS = {
  consensus: "Consensus reached",
  judge_decision: "Judge's decision",
  forced_ruling: "Forced ruling at round cap",
  fallback: "Mechanical fallback",
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// Anonymous per-browser id; scopes mission history to this browser (not authentication).
let memoryClientId = null;
function clientId() {
  try {
    let id = localStorage.getItem("etocelest.clientId");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("etocelest.clientId", id);
    }
    return id;
  } catch {
    memoryClientId ||= crypto.randomUUID();
    return memoryClientId;
  }
}

async function errorFrom(res) {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d) => d.msg).join("; ");
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(message, res.status);
}

async function request(path, { method = "GET", body, signal } = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      signal,
      headers: { "X-Client-Id": clientId(), ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError("Cannot reach the ÉTOCELEST server. Check that the backend is running.", 0);
  }
  if (!res.ok) throw await errorFrom(res);
  return res.status === 204 ? null : res.json();
}

export const getHealth = (opts) => request("/api/health", opts);
export const fetchPresets = () => request("/api/presets");
export const submitMission = ({ name, launchDate, context }) =>
  request("/api/missions", { method: "POST", body: { name, launchDate, context } }); // -> { missionId }
export const getMission = (id) => request(`/api/missions/${encodeURIComponent(id)}`);
export const listMissions = () => request("/api/missions");
export const deleteMission = (id) => request(`/api/missions/${encodeURIComponent(id)}`, { method: "DELETE" });
export const retryMission = (id) => request(`/api/missions/${encodeURIComponent(id)}/retry`, { method: "POST" });

// --- SSE over fetch (lets us send the X-Client-Id header and control reconnects) --------

async function readSse(body, onFrame) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return false;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let id = null;
      const data = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("id:")) id = Number(line.slice(3).trim());
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length && onFrame(id, JSON.parse(data.join("\n")))) return true;
    }
  }
}

const sleep = (ms, signal) =>
  new Promise((resolve) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); resolve(); }, { once: true });
  });

/**
 * Follows the debate stream, replaying persisted events from the start and then live.
 * Reconnects with the last event id on network drops. Resolves after a terminal
 * event (`done`/`error`) or abort; rejects on non-recoverable failure.
 */
export async function runMissionDebate(missionId, onEvent, { signal } = {}) {
  let cursor = 0;
  let failures = 0;
  while (!signal?.aborted) {
    try {
      const res = await fetch(`${BASE_URL}/api/missions/${encodeURIComponent(missionId)}/stream?after=${cursor}`, {
        signal,
        headers: { "X-Client-Id": clientId(), Accept: "text/event-stream" },
      });
      if (!res.ok) throw await errorFrom(res);
      const terminal = await readSse(res.body, (id, evt) => {
        if (id) cursor = id;
        failures = 0;
        onEvent(evt);
        return evt.type === "done" || evt.type === "error";
      });
      if (terminal) return;
      failures += 1; // stream closed cleanly without a terminal event
    } catch (err) {
      if (signal?.aborted || err.name === "AbortError") return;
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) throw err;
      failures += 1;
    }
    if (failures > 6) throw new ApiError("Lost connection to the ÉTOCELEST server.", 0);
    await sleep(Math.min(1000 * 2 ** failures, 10000), signal);
  }
}
