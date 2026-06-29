import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { LOGO_URL } from "../assets/placeholder-logo";

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError("Usuário ou senha incorretos");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%)",
    }}>
      <div style={{
        background: "#1e293b",
        padding: "3rem",
        borderRadius: "12px",
        boxShadow: "0 20px 25px -5px rgba(0,0,0,0.3)",
        width: "100%",
        maxWidth: "400px",
      }}>
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <img 
            src={LOGO_URL} 
            alt="C&A Soluções em Copiadoras"
            style={{
              width: "320px",
              height: "auto",
              borderRadius: "0",
              objectFit: "contain",
              marginBottom: "2rem",
              backgroundColor: "transparent",
              mixBlendMode: "multiply",
              filter: "brightness(1.2) saturate(1.3)",
            }}
          />
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "1.5rem" }}>
            <label style={{
              display: "block",
              color: "#94a3b8",
              marginBottom: "0.5rem",
              fontSize: "0.875rem",
            }}>Usuário</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                border: "1px solid #334155",
                background: "#0f172a",
                color: "#fff",
                fontSize: "1rem",
                outline: "none",
                transition: "border-color 0.2s",
              }}
              onFocus={(e) => e.target.style.borderColor = "#3b82f6"}
              onBlur={(e) => e.target.style.borderColor = "#334155"}
            />
          </div>

          <div style={{ marginBottom: "1.5rem" }}>
            <label style={{
              display: "block",
              color: "#94a3b8",
              marginBottom: "0.5rem",
              fontSize: "0.875rem",
            }}>Senha</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                border: "1px solid #334155",
                background: "#0f172a",
                color: "#fff",
                fontSize: "1rem",
                outline: "none",
                transition: "border-color 0.2s",
              }}
              onFocus={(e) => e.target.style.borderColor = "#3b82f6"}
              onBlur={(e) => e.target.style.borderColor = "#334155"}
            />
          </div>

          {error && (
            <div style={{
              color: "#ef4444",
              fontSize: "0.875rem",
              marginBottom: "1rem",
              textAlign: "center",
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "0.875rem",
              borderRadius: "8px",
              background: "#3b82f6",
              color: "#fff",
              fontSize: "1rem",
              fontWeight: "600",
              border: "none",
              cursor: "pointer",
              transition: "background-color 0.2s",
              opacity: loading ? 0.5 : 1,
            }}
            onMouseOver={(e) => {
              if (!loading) e.currentTarget.style.background = "#2563eb";
            }}
            onMouseOut={(e) => {
              if (!loading) e.currentTarget.style.background = "#3b82f6";
            }}
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
