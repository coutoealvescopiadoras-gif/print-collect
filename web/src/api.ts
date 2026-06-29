const BASE = import.meta.env.VITE_API_URL || "";

let token: string | null = null;

export function setAuthToken(newToken: string | null) {
  token = newToken;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE}${path}`, {
    headers: { ...headers, ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

export const api = {
  login: (username: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    return request<{ access_token: string; token_type: string }>("/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });
  },
  getMe: () => request<import("./types").User>("/api/users/me"),
  getStats: () => request<import("./types").DashboardStats>("/api/dashboard/stats"),
  getClients: () => request<import("./types").Client[]>("/api/clients"),
  createClient: (data: Partial<import("./types").Client>) =>
    request<import("./types").Client>("/api/clients", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getPrinters: (clientId?: number) =>
    request<import("./types").Printer[]>(
      clientId ? `/api/printers?client_id=${clientId}` : "/api/printers",
    ),
  getAlerts: (resolved?: boolean) =>
    request<import("./types").Alert[]>(
      resolved !== undefined ? `/api/alerts?resolved=${resolved}` : "/api/alerts",
    ),
  resolveAlert: (id: number) =>
    request<import("./types").Alert>(`/api/alerts/${id}/resolve`, { method: "POST" }),
  getAgents: () => request<import("./types").Agent[]>("/api/agents"),
  createAgent: (clientId: number, name: string) =>
    request<import("./types").Agent>("/api/agents", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, name }),
    }),
};
