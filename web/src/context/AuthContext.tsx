import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, setAuthToken } from "../api";
import type { User } from "../types";

interface AuthContextType {
  user: User | null;
  token: string | null;
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

const INITIAL_TOKEN: string | null =
  typeof window !== "undefined" ? window.localStorage.getItem("token") : null;

if (INITIAL_TOKEN) {
  setAuthToken(INITIAL_TOKEN);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(INITIAL_TOKEN);
  const [loading, setLoading] = useState(true);

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
        if (!cancelled) setLoading(false);
      } catch (err) {
        if (cancelled) return;

        // 🔴 RETRY AUTOMÁTICO: até 3 tentativas com intervalo de 600ms
        // para casos de rede instável, timeout, ou erro transitório.
        // Só desiste DEPOIS de 3 tentativas falhadas!
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

        // 🔴 FIX NUCLEAR: NUNCA MAIS APAGAR O TOKEN DO localStorage NO catch()!
        // Motivo: Qualquer erro TRANSITÓRIO apagava um token VÁLIDO e causava deslogue no F5!
        // Token SÓ é apagado quando usuário clica EXPLICITAMENTE em "Sair" (função logout).
        console.error(
          "❌ AuthContext: getMe falhou em todas as 3 tentativas. Mantendo token salvo para retry manual (F5)...",
          err
        );
        // SÓ apaga o `user` do state (UI vai redirecionar pro login via ProtectedRoutes),
        // mas MANTÉM token em localStorage e no módulo api!
        setToken(INITIAL_TOKEN);
        setUser(null);
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
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    window.localStorage.removeItem("token");
    setAuthToken(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
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
