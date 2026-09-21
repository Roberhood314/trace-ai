const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

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
    headers: {
      "Content-Type": "application/json",
      "X-Role": "analyst",
    },
    body: JSON.stringify(payload),
  });
}

export async function fetchCases() {
  return request("/cases", {
    headers: { "X-Role": "viewer" },
  });
}
