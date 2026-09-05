function isLocalNetworkHost(hostname: string) {
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return true;
  }

  return (
    /^10(?:\.\d{1,3}){3}$/.test(hostname) ||
    /^192\.168(?:\.\d{1,3}){2}$/.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}$/.test(hostname)
  );
}

function isVercelPreview(hostname: string) {
  return /\.vercel\.app$/.test(hostname) || /-git-[a-f0-9]+-/.test(hostname);
}

export function resolveBaseUrl() {
  const STORAGE_KEY = "pc_debug_api_url";

  // ==================================================================
  // NIVEIS DE PRIORIDADE (DE MAIOR para MENOR):
  //   A) localStorage pc_debug_api_url → MENU SECRETO Login.tsx (clica 7x no logo PrintCollect!)
  //      Julio tem o POD TOTAL de escolher a URL que quiser.
  //   B) import.meta.env.VITE_API_URL → Painel Vercel Settings / .env
  //   C) Regras do dominio (printcollect.com.br = VERCEL SERVERLESS FUNCTION etc)
  // ==================================================================
  if (typeof window !== "undefined") {
    const debugOverride = (window.localStorage.getItem(STORAGE_KEY) || "").trim();
    if (debugOverride) {
      return debugOverride.replace(/\/$/, "");
    }
  }

  const configuredBase = (import.meta.env.VITE_API_URL || "").trim();

  if (configuredBase) {
    if (typeof window === "undefined") {
      return configuredBase;
    }

    try {
      const url = new URL(configuredBase);
      const isLocalApiHost = isLocalNetworkHost(url.hostname);
      const isLocalPageHost = isLocalNetworkHost(window.location.hostname);

      if (isLocalApiHost && isLocalPageHost) {
        url.hostname = window.location.hostname;
        return url.toString().replace(/\/$/, "");
      }
    } catch {
      return configuredBase;
    }

    return configuredBase.replace(/\/$/, "");
  }

  if (typeof window === "undefined") {
    return "";
  }

  const host = window.location.hostname;
  const proto = window.location.protocol;

  // ============================================================
  // NENHUMA variavel VITE_API_URL configurada (CASO ATUAL).
  // Volta ao comportamento ORIGINAL (funcionava antes das alteracoes):
  // - Producao printcollect.com.br / www.printcollect.com.br:
  //   BASE VAZIA ("") = usa /api/* no MESMO dominio → Serverless Function
  //   Python da Vercel (api/index.py). Ja corrigimos ReadingOut no routes.py.
  // - Preview Vercel: vazio (a menos que VITE_API_URL_FALLBACK esteja setado)
  // - OnRender / Local / LAN: comportamento padrao.
  //
  // Julio pode a QUALQUER MOMENTO ativar backend dedicado no Render criando
  // a variavel VITE_API_URL = https://print-collect.onrender.com no
  // painel Settings Environment Variables da Vercel (Production + Preview).
  // ============================================================

  if (host === "printcollect.com.br" || host === "www.printcollect.com.br") {
    return "https://print-collect.onrender.com";
  }

  if (isVercelPreview(host) || host.endsWith(".vercel.app")) {
    const fallback = (import.meta.env.VITE_API_URL_FALLBACK || "").trim();
    if (fallback) return fallback.replace(/\/$/, "");
    return "https://print-collect.onrender.com";
  }

  if (host.endsWith(".onrender.com")) {
    return `${proto}//${host}`;
  }

  if (isLocalNetworkHost(host)) {
    return `${proto}//${host}:8000`;
  }

  return "";
}

const BASE = resolveBaseUrl();

let token: string | null =
  typeof window !== "undefined" ? window.localStorage.getItem("token") : null;

export function getApiBaseUrl() {
  return BASE;
}

export function getPublicApiUrl() {
  if (BASE) return BASE.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "printcollect.com.br" || host === "www.printcollect.com.br" || host.endsWith(".vercel.app")) {
      return `${window.location.protocol}//${host}`;
    }
    if (host.endsWith(".onrender.com")) {
      return `${window.location.protocol}//${host}`;
    }
    const fb = (import.meta.env.VITE_API_URL_FALLBACK || "").trim();
    if (fb) return fb.replace(/\/$/, "");
  }
  return "";
}

export function setAuthToken(newToken: string | null) {
  token = newToken;
  if (typeof window !== "undefined") {
    if (newToken) {
      window.localStorage.setItem("token", newToken);
    } else {
      window.localStorage.removeItem("token");
    }
  }
}

function readTokenFromStorage(): string | null {
  if (typeof window === "undefined") return token;
  const stored = window.localStorage.getItem("token");
  if (stored !== token) token = stored;
  return token;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const RETRYABLE_STATUS = new Set([404, 500, 502, 503, 504]);
  const MAX_RETRIES = 2;
  const RETRY_DELAY_MS = 800;

  let lastError: unknown = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const headers: Record<string, string> = { "Content-Type": "application/json" };

    const currentToken = readTokenFromStorage();
    if (currentToken) {
      headers["Authorization"] = `Bearer ${currentToken}`;
    }

    const response = await fetch(`${BASE}${path}`, {
      headers: { ...headers, ...options?.headers },
      ...options,
    });

    if (response.ok) {
      return response.json();
    }

    const text = await response.text();
    lastError = new Error(text || response.statusText);

    const shouldRetry = attempt < MAX_RETRIES && RETRYABLE_STATUS.has(response.status);
    if (shouldRetry) {
      // Delay + retry (evita 404 de cold-start da Vercel / Render)
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
      continue;
    }

    throw lastError;
  }

  throw lastError;
}

/**
 * Download AUTENTICADO de CSV/arquivo via Blob + trigger click a tag.
 * Usa o mesmo token do request() para passar pela proteção de rotas.
 */
async function _downloadAuthenticated(path: string, fallbackFileName: string): Promise<void> {
  const headers: Record<string, string> = {};
  const currentToken = readTokenFromStorage();
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }
  const response = await fetch(`${BASE}${path}`, { headers });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `Erro ${response.status} no download`);
  }
  const blob = await response.blob();
  // Tenta extrair filename do Content-Disposition
  let fileName = fallbackFileName;
  try {
    const cd = response.headers.get("Content-Disposition") || "";
    const m = /filename="?([^";]+)"?/.exec(cd);
    if (m && m[1]) fileName = m[1];
  } catch {}
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => {
    try {
      window.URL.revokeObjectURL(url);
    } catch {}
  }, 5000);
}

export const api = {
  login: (email: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    return request<{ access_token: string; token_type: string }>("/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    });
  },
  getMe: () => request<import("./types").User>("/api/users/me"),
  changeOwnPassword: (currentPassword: string, newPassword: string) =>
    request<{ status: string }>("/api/users/me/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  getUsers: () => request<import("./types").User[]>("/api/users"),
  createUser: (data: {
    username?: string;
    email: string;
    password: string;
    role: "superadmin" | "partner_admin" | "partner_staff" | "client_manager" | "client_viewer";
    client_id?: number | null;
    partner_id?: number | null;
  }) =>
    request<import("./types").User>("/api/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateUser: (
    userId: number,
    data: Partial<{
      email: string;
      password: string;
      role: "superadmin" | "partner_admin" | "partner_staff" | "client_manager" | "client_viewer";
      client_id: number | null;
      partner_id: number | null;
      active: boolean;
    }>,
  ) =>
    request<import("./types").User>(`/api/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteUser: (userId: number) =>
    request<{ status: string; message: string; user_id: number; email: string }>(`/api/users/${userId}`, { method: "DELETE" }),
  getStats: () => request<import("./types").DashboardStats>("/api/dashboard/stats"),
  getClients: (params?: {
    search?: string;
    partner_id?: number;
    own_only?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params) {
      if (params.search) qs.set("search", params.search);
      if (params.partner_id !== undefined && params.partner_id !== null)
        qs.set("partner_id", String(params.partner_id));
      if (params.own_only !== undefined && params.own_only !== null)
        qs.set("own_only", params.own_only ? "1" : "0");
    }
    const q = qs.toString();
    return request<import("./types").Client[]>(
      q ? `/api/clients?${q}` : "/api/clients",
    );
  },
  createClient: (data: Partial<import("./types").Client>) =>
    request<import("./types").Client>("/api/clients", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateClient: (
    clientId: number,
    data: Partial<Pick<import("./types").Client, "name" | "cnpj" | "contact_name" | "contact_email" | "active">>,
  ) =>
    request<import("./types").Client>(`/api/clients/${clientId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteClient: (clientId: number) =>
    request<{ status: string }>(`/api/clients/${clientId}`, { method: "DELETE" }),
  getLocations: (clientId: number) =>
    request<import("./types").Location[]>(`/api/clients/${clientId}/locations`),
  createLocation: (data: {
    client_id: number;
    name: string;
    sector?: string | null;
    responsible?: string | null;
    address?: string | null;
  }) =>
    request<import("./types").Location>("/api/locations", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updatePrinter: (
    printerId: number,
    data: Partial<{
      ip_address: string;
      mac_address: string;
      serial_number: string;
      model: string;
      manufacturer: string;
      location_id: number | null;
      status: string;
    }>,
  ) =>
    request<import("./types").Printer>(`/api/printers/${printerId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  ignorePrinter: (printerId: number) =>
    request<import("./types").Printer>(`/api/printers/${printerId}/ignore`, {
      method: "POST",
    }),
  normalizePrinterForPinch: (printerId: number) =>
    request<import("./types").Printer>(`/api/printers/${printerId}/normalize_for_pinch`, {
      method: "POST",
    }),
  forceSetPrinterTotal: (printerId: number, pages_total: number) =>
    request<import("./types").Printer>(`/api/printers/${printerId}/force_set_total`, {
      method: "POST",
      body: JSON.stringify({ pages_total }),
    }),
  getPrinters: (params?: {
    client_id?: number;
    partner_id?: number;
    search?: string;
    own_only?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params) {
      if (params.client_id !== undefined && params.client_id !== null)
        qs.set("client_id", String(params.client_id));
      if (params.partner_id !== undefined && params.partner_id !== null)
        qs.set("partner_id", String(params.partner_id));
      if (params.search) qs.set("search", params.search);
      if (params.own_only !== undefined && params.own_only !== null)
        qs.set("own_only", params.own_only ? "1" : "0");
    }
    const q = qs.toString();
    return request<import("./types").Printer[]>(
      q ? `/api/printers?${q}` : "/api/printers",
    );
  },
  getPrinterById: (printerId: number) =>
    request<import("./types").Printer>(`/api/printers/${printerId}`),
  getPrinterReadings: (printerId: number, limit = 50) =>
    request<import("./types").Reading[]>(`/api/printers/${printerId}/readings?limit=${limit}`),

  // ----- EXPORT CSV DOWNLOADS (usa fetch com token + blob download) -----
  downloadPrinterReadingsCSV: async (printerId: number, filtros?: {
    data_inicio?: string;
    data_fim?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (filtros) {
      if (filtros.data_inicio) qs.set("data_inicio", filtros.data_inicio);
      if (filtros.data_fim) qs.set("data_fim", filtros.data_fim);
      if (filtros.limit != null) qs.set("limit", String(filtros.limit));
    }
    const q = qs.toString();
    const path = q ? `/api/printers/${printerId}/readings/csv?${q}` : `/api/printers/${printerId}/readings/csv`;
    return _downloadAuthenticated(path, `leituras_impressora_${printerId}.csv`);
  },
  downloadHistoricoColetasCSV: async (filtros?: {
    printer_id?: number;
    cliente_id?: number;
    status_coleta?: string;
    data_inicio?: string;
    data_fim?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (filtros) {
      if (filtros.printer_id != null) qs.set("printer_id", String(filtros.printer_id));
      if (filtros.cliente_id != null) qs.set("cliente_id", String(filtros.cliente_id));
      if (filtros.status_coleta) qs.set("status_coleta", filtros.status_coleta);
      if (filtros.data_inicio) qs.set("data_inicio", filtros.data_inicio);
      if (filtros.data_fim) qs.set("data_fim", filtros.data_fim);
      if (filtros.limit != null) qs.set("limit", String(filtros.limit));
    }
    const q = qs.toString();
    const path = q ? `/api/historico-coletas.csv?${q}` : "/api/historico-coletas.csv";
    return _downloadAuthenticated(path, "historico_coletas.csv");
  },
  getAlerts: (resolved?: boolean) =>
    request<import("./types").Alert[]>(
      resolved !== undefined ? `/api/alerts?resolved=${resolved}` : "/api/alerts",
    ),
  resolveAlert: (id: number) =>
    request<import("./types").Alert>(`/api/alerts/${id}/resolve`, { method: "POST" }),
  getBrandingMe: () =>
    request<{
      display_name: string;
      logo_src: string | null;
      tagline: string;
      partner_id: number | null;
      partner_name: string | null;
      client_id: number | null;
      client_name: string | null;
      role_label: string;
    }>("/api/branding/me"),
  getAgents: () => request<import("./types").Agent[]>("/api/agents"),
  getPartners: () => request<import("./types").Partner[]>("/api/partners"),
  getPartnerStats: () => request<import("./types").PartnerBillingStats[]>("/api/partners/stats"),
  createPartner: (data: Partial<import("./types").Partner>) =>
    request<import("./types").Partner>("/api/partners", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updatePartner: (
    partnerId: number,
    data: Partial<import("./types").Partner>,
  ) =>
    request<import("./types").Partner>(`/api/partners/${partnerId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deletePartner: (partnerId: number) =>
    request<{
      status: string;
      message: string;
      partner_id: number;
      partner_name: string;
    }>(`/api/partners/${partnerId}`, { method: "DELETE" }),
  createAgent: (clientId: number, name: string) =>
    request<import("./types").Agent>("/api/agents", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, name }),
    }),
  generateAgentPairingCode: (payload: {
    client_id: number;
    name?: string;
    ttl_minutes?: number;
  }) =>
    request<import("./types").AgentPairingCode>("/api/agents/pairing/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteAgent: (agentId: number) =>
    request<{ status: string }>(`/api/agents/${agentId}`, { method: "DELETE" }),
  downloadAgentWindowsPackage: async (agentId: number) => {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(`${BASE}/api/agents/${agentId}/windows-package`, {
      headers,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    const blob = await response.blob();
    const contentDisposition = response.headers.get("Content-Disposition") || "";
    return { blob, contentDisposition };
  },
};
