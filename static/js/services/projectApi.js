const API_BASE = "/api";

function authHeaders() {
  const token = window.localStorage.getItem("authToken");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "REQUEST_FAILED");
  }
  return response.json();
}

export async function fetchProjects() {
  return request("/projects", { method: "GET" });
}

export async function createProject(payload) {
  return request("/projects", { method: "POST", body: JSON.stringify(payload) });
}

export async function upsertMpzp(projectId, payload) {
  return request(`/projects/${projectId}/mpzp`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function getCostEstimate(projectId) {
  return request(`/projects/${projectId}/cost-estimate`, { method: "GET" });
}

export async function createCostItem(projectId, payload) {
  return request(`/projects/${projectId}/cost-estimate/items`, { method: "POST", body: JSON.stringify(payload) });
}

export async function fetchDesignAssets(projectId) {
  return request(`/projects/${projectId}/design-assets`, { method: "GET" });
}
