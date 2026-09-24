const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
let sessionToken = localStorage.getItem("trace_ai_session") || "";

export function setSessionToken(token) {
  sessionToken = token || "";
  if (sessionToken) localStorage.setItem("trace_ai_session", sessionToken);
  else localStorage.removeItem("trace_ai_session");
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (sessionToken) headers.Authorization = `Bearer ${sessionToken}`;
  return headers;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

export async function verifyPiAccessToken(accessToken) {
  const result = await request("/auth/pi/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
  });
  setSessionToken(result.token);
  return result;
}

export async function testPaymentConfig() { return request("/pi/test-payment/config"); }
export async function approveTestPayment(paymentId) {
  return request("/pi/test-payment/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payment_id: paymentId }) });
}
export async function completeTestPayment(paymentId, txid) {
  return request("/pi/test-payment/complete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payment_id: paymentId, txid }) });
}

export async function createCase(payload) {
  return request("/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export async function fetchCases() { return request("/cases"); }

export async function createPerson(caseId, payload) {
  return request(`/cases/${caseId}/person`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export async function fetchPerson(caseId) { return request(`/cases/${caseId}/person`); }

export async function createTimelineEvent(caseId, payload) {
  return request(`/cases/${caseId}/timeline`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export async function fetchTimeline(caseId) { return request(`/cases/${caseId}/timeline`); }

export async function createZone(caseId, payload) {
  return request(`/cases/${caseId}/search-zones`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export async function fetchZones(caseId) { return request(`/cases/${caseId}/search-zones`); }

export async function fetchEvidence(caseId) { return request(`/cases/${caseId}/evidence`); }
export async function uploadEvidence(caseId, file, note = "") {
  const body = new FormData();
  body.append("file", file);
  if (note) body.append("note", note);
  return request(`/cases/${caseId}/evidence`, { method: "POST", body });
}
export async function fetchEvidenceBlob(path) {
  const response = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!response.ok) throw new Error("Không thể tải chứng cứ");
  return response.blob();
}

export async function fetchAiSummary(caseId) { return request(`/cases/${caseId}/ai-summary`); }
export async function fetchAudit(caseId) { return request(`/cases/${caseId}/audit`); }
export async function fetchUsers() { return request("/users"); }
export async function updateUser(userId, payload) {
  return request(`/users/${userId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export async function fetchWanted(q = "", limit = 100) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("limit", String(limit));
  return request(`/wanted?${params.toString()}`);
}
export async function fetchWantedSourceStatus() {
  return request("/wanted/source-status");
}
export async function syncWanted(pages = 3) {
  return request(`/wanted/sync?pages=${pages}`, { method: "POST" });
}


export async function fetchFusionStatus() { return request("/fusion/status"); }
export async function fetchFusionTracks(limit = 100) { return request(`/fusion/tracks?limit=${limit}`); }
export async function fetchFusionTrajectory(trackId, limit = 200) { return request(`/fusion/tracks/${trackId}/trajectory?limit=${limit}`); }
export async function reviewFusionTrack(trackId, decision, note = "") {
  return request(`/fusion/tracks/${trackId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note }),
  });
}
export async function createFusionGeofence(payload) {
  return request("/fusion/geofences", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
