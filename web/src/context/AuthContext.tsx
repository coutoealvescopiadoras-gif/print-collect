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

    async function bootstrap() {
      if (!INITIAL_TOKEN) {
        if (!cancelled) setLoading(false);
        return;
      }

      try {
        setAuthToken(INITIAL_TOKEN);
        const userData = await api.getMe();
        if (cancelled) return;
        setUser(normalizeUser(userData));
      } catch (err) {
        if (cancelled) return;
        console.error("❌ AuthContext: token invalido/expirado. Limpando.", err);
        setToken(null);
        setUser(null);
        window.localStorage.removeItem("token");
        setAuthToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    bootstrap();

    return () => {
      cancelled = true;
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
