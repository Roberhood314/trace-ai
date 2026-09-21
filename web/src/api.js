const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

const viewerHeaders = { "X-Role": "viewer" };
const analystHeaders = { "X-Role": "analyst" };

export async function verifyPiAccessToken(accessToken) {
  return request("/auth/pi/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
  });
}

export async function createCase(payload) {
  return request("/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...analystHeaders },
    body: JSON.stringify(payload),
  });
}

export async function fetchCases() {
  return request("/cases", { headers: viewerHeaders });
}

export async function createPerson(caseId, payload) {
  return request(`/cases/${caseId}/person`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...analystHeaders },
    body: JSON.stringify(payload),
  });
}

export async function fetchPerson(caseId) {
  return request(`/cases/${caseId}/person`, { headers: viewerHeaders });
}

export async function fetchTimeline(caseId) {
  return request(`/cases/${caseId}/timeline`, { headers: viewerHeaders });
}

export async function fetchZones(caseId) {
  return request(`/cases/${caseId}/search-zones`, { headers: viewerHeaders });
}

export async function fetchEvidence(caseId) {
  return request(`/cases/${caseId}/evidence`, { headers: viewerHeaders });
}

export async function uploadEvidence(caseId, file, note = "") {
  const body = new FormData();
  body.append("file", file);
  if (note) body.append("note", note);

  return request(`/cases/${caseId}/evidence`, {
    method: "POST",
    headers: analystHeaders,
    body,
  });
}

export function absoluteAssetUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path}`;
}
