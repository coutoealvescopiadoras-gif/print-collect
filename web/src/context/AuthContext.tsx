import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, setAuthToken } from "../api";

interface User {
  id: number;
  username: string;
  email: string;
  active: boolean;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setAuthToken(token);
    if (token) {
      api.getMe().then(setUser).catch(() => {
        setToken(null);
        localStorage.removeItem("token");
        setAuthToken(null);
      }).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (username: string, password: string) => {
    const response = await api.login(username, password);
    const newToken = response.access_token;
    setToken(newToken);
    localStorage.setItem("token", newToken);
    setAuthToken(newToken);
    const userData = await api.getMe();
    setUser(userData);
  };

  const logout = () => {
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
