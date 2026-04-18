/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Uses VITE_API_URL from env, defaults to http://localhost:8000/api.
 * Every method throws on non-2xx so callers can try/catch uniformly.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const DEFAULT_TIMEOUT_MS = 30_000;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  health: () => request("/health"),

  // Orders
  getOrders: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/orders${qs ? "?" + qs : ""}`);
  },
  getOrder: (orderId) => request(`/orders/${orderId}`),
  createOrder: (payload) =>
    request("/orders", { method: "POST", body: JSON.stringify(payload) }),
  processOrder: (orderId) =>
    request("/process-order", { method: "POST", body: JSON.stringify({ order_id: orderId }) }),
  processAll: () => request("/process-all-orders", { method: "POST" }),

  // Inventory
  getInventory: () => request("/inventory"),
  getProduct: (productId) => request(`/inventory/${productId}`),
  updateStock: (payload) =>
    request("/update-stock", { method: "POST", body: JSON.stringify(payload) }),
  getRestockSuggestions: () => request("/restock-suggestions"),

  // Alerts
  getAlerts: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/alerts${qs ? "?" + qs : ""}`);
  },
  acknowledgeAlert: (id) =>
    request("/alerts/acknowledge", { method: "POST", body: JSON.stringify({ alert_id: id }) }),

  // Agents
  getAgentLogs: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/agent-logs${qs ? "?" + qs : ""}`);
  },

  // Dashboard
  getStats: () => request("/dashboard/stats"),
};
