import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, setAuthToken } from "../api";
import type { User } from "../types";
import { LOGO_URL as FALLBACK_LOGO_URL } from "../assets/placeholder-logo";

export type Branding = {
  display_name: string;
  logo_src: string;
  tagline: string;
  partner_id: number | null;
  partner_name: string | null;
  client_id: number | null;
  client_name: string | null;
  role_label: string;
};

interface AuthContextType {
  user: User | null;
  token: string | null;
  branding: Branding | null; // null = ainda nao carregou (NAO EXIBE NADA)
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function normalizeUser(user: User): User {
  return {
    ...user,
    role: user.role || "superadmin",
    client_id: user.client_id ?? null,
  };
}

const DEFAULT_BRANDING: Branding = {
  display_name: "C&A Soluções",
  logo_src: FALLBACK_LOGO_URL,
  tagline: "Monitoramento de Impressoras",
  partner_id: null,
  partner_name: null,
  client_id: null,
  client_name: null,
  role_label: "Superadmin",
};

function safeDocumentTitle(displayName: string, tagline: string) {
  if (typeof document === "undefined") return;
  const hasTagline = tagline && tagline !== displayName;
  document.title = hasTagline ? `${displayName} — ${tagline} | Print Collect` : `${displayName} | Print Collect`;
}

const INITIAL_TOKEN: string | null =
  typeof window !== "undefined" ? window.localStorage.getItem("token") : null;

if (INITIAL_TOKEN) {
  setAuthToken(INITIAL_TOKEN);
}

const BRANDING_CACHE_KEY = "pc_branding_cache_v1";

function loadInitialBrandingFromCache(): Branding | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(BRANDING_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Branding;
    if (!parsed || typeof parsed !== "object") return null;
    const sanitized: Branding = {
      display_name: parsed.display_name || DEFAULT_BRANDING.display_name,
      logo_src: parsed.logo_src || DEFAULT_BRANDING.logo_src,
      tagline: parsed.tagline || DEFAULT_BRANDING.tagline,
      partner_id: parsed.partner_id ?? null,
      partner_name: parsed.partner_name ?? null,
      client_id: parsed.client_id ?? null,
      client_name: parsed.client_name ?? null,
      role_label: parsed.role_label || DEFAULT_BRANDING.role_label,
    };
    // Seguranca: Se tem token inicial, NÃO RETORNAR LOGO AINDA (evita piscada em transicao).
    // Vamos retornar null e deixar o guard no Layout cobrir. A proxima pintura ja vem correta.
    if (INITIAL_TOKEN) return null;
    return sanitized;
  } catch {
    return null;
  }
}

function saveBrandingCache(b: Branding) {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(BRANDING_CACHE_KEY, JSON.stringify(b));
  } catch {
    /* noop */
  }
}

function clearBrandingCache() {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(BRANDING_CACHE_KEY);
  } catch {
    /* noop */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(INITIAL_TOKEN);
  // ⛔ branding INICIAL = null (NAO TEM DEFAULT C&A!)
  // Assim NUNCA pinta tela com a logo errada, nem por 1 frame.
  const [branding, setBranding] = useState<Branding | null>(() => loadInitialBrandingFromCache());
  // ⛔ loading INICIAL = TRUE SEMPRE que existir token (nao ha usuario sem carregar)
  const [loading, setLoading] = useState<boolean>(!!INITIAL_TOKEN);

  useEffect(() => {
    safeDocumentTitle(DEFAULT_BRANDING.display_name, DEFAULT_BRANDING.tagline);
  }, []);

  async function loadBrandingIfLoggedIn() {
    try {
      const b = await api.getBrandingMe();
      const merged: Branding = {
        display_name: b.display_name || DEFAULT_BRANDING.display_name,
        logo_src: b.logo_src || DEFAULT_BRANDING.logo_src,
        tagline: b.tagline || DEFAULT_BRANDING.tagline,
        partner_id: b.partner_id ?? null,
        partner_name: b.partner_name ?? null,
        client_id: b.client_id ?? null,
        client_name: b.client_name ?? null,
        role_label: b.role_label || DEFAULT_BRANDING.role_label,
      };
      // ✅ Agora branding NUNCA é null!
      setBranding(merged);
      saveBrandingCache(merged);
      safeDocumentTitle(merged.display_name, merged.tagline);
    } catch (e) {
      // ✅ Fallback: mesmo com erro, mostra a C&A (sem null para nao travar guard)
      setBranding(DEFAULT_BRANDING);
      saveBrandingCache(DEFAULT_BRANDING);
      safeDocumentTitle(DEFAULT_BRANDING.display_name, DEFAULT_BRANDING.tagline);
    }
  }

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    async function bootstrap(retryCount = 0) {
      if (!INITIAL_TOKEN) {
        if (!cancelled) setLoading(false);
        return;
      }

      try {
        setAuthToken(INITIAL_TOKEN);
        const userData = await api.getMe();
        if (cancelled) return;
        setUser(normalizeUser(userData));
        await loadBrandingIfLoggedIn();
        if (!cancelled) setLoading(false);
      } catch (err) {
        if (cancelled) return;

        if (retryCount < 3) {
          console.warn(
            `⚠️ AuthContext: getMe falhou (tentativa ${retryCount + 1}/3). Retentando em 600ms...`,
            err
          );
          retryTimer = window.setTimeout(() => {
            if (!cancelled) bootstrap(retryCount + 1);
          }, 600);
          return;
        }

        console.error(
          "❌ AuthContext: getMe falhou em todas as 3 tentativas. Mantendo token salvo para retry manual (F5)...",
          err
        );
        setToken(INITIAL_TOKEN);
        setUser(null);
        // ⛔ Token invalido: branding null para nao mostrar logo nenhuma
        setBranding(null);
        clearBrandingCache();
        safeDocumentTitle(DEFAULT_BRANDING.display_name, DEFAULT_BRANDING.tagline);
        if (!cancelled) setLoading(false);
      }
    }

    bootstrap();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, []);

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password);
    const newToken = response.access_token;
    window.localStorage.setItem("token", newToken);
    setAuthToken(newToken);
    setToken(newToken);
    const userData = await api.getMe();
    setUser(normalizeUser(userData));
    await loadBrandingIfLoggedIn();
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    window.localStorage.removeItem("token");
    setAuthToken(null);
    // ⛔ Ao sair: branding volta para null (para a pagina de login pintar a generica)
    setBranding(null);
    clearBrandingCache();
    safeDocumentTitle(DEFAULT_BRANDING.display_name, DEFAULT_BRANDING.tagline);
  };

  return (
    <AuthContext.Provider value={{ user, token, branding, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
