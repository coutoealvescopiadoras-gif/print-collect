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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log("🔑 AuthContext: token inicial:", token);
    setAuthToken(token);
    if (token) {
      console.log("🔑 AuthContext: tentando obter dados do usuário...");
      api.getMe().then((userData) => {
        console.log("✅ AuthContext: dados do usuário obtidos com sucesso!", userData);
        setUser(normalizeUser(userData));
      }).catch((err) => {
        console.error("❌ AuthContext: erro ao obter dados do usuário!", err);
        setToken(null);
        localStorage.removeItem("token");
        setAuthToken(null);
      }).finally(() => setLoading(false));
    } else {
      console.log("🔑 AuthContext: nenhum token encontrado");
      setLoading(false);
    }
  }, [token]);

  const login = async (email: string, password: string) => {
    console.log("🔑 Login: tentando login com e-mail:", email);
    const response = await api.login(email, password);
    console.log("✅ Login: token obtido com sucesso!", response);
    const newToken = response.access_token;
    setToken(newToken);
    localStorage.setItem("token", newToken);
    setAuthToken(newToken);
    console.log("🔑 Login: obtendo dados do usuário...");
    const userData = await api.getMe();
    console.log("✅ Login: dados do usuário obtidos com sucesso!", userData);
    setUser(normalizeUser(userData));
  };

  const logout = () => {
    console.log("🔑 Logout: limpando dados do usuário");
    setUser(null);
    setToken(null);
    localStorage.removeItem("token");
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
