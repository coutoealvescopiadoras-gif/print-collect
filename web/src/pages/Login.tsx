import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { PRINT_COLLECT_LOGO } from "../assets/placeholder-logo";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login ou senha incorretos");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <img
            src={PRINT_COLLECT_LOGO}
            alt="Print Collect - Monitoramento Automático"
            style={{
              width: "380px",
              height: "auto",
              borderRadius: "0",
              objectFit: "contain",
              maxWidth: "100%",
            }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).src = PRINT_COLLECT_LOGO;
            }}
          />
          <p
            style={{
              color: "var(--text-muted)",
              fontSize: "0.95rem",
              marginTop: "0.5rem",
              marginBottom: 0,
            }}
          >
            Painel de Monitoramento Automático de Contadores de Impressoras
          </p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label>E-mail</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="seu@email.com"
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label>Senha</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              disabled={loading}
            />
          </div>

          {error && <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>{error}</div>}
          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
