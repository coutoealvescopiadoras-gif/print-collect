import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { LOGO_URL as DEFAULT_LOGO_URL } from "../assets/placeholder-logo";

const DEFAULT_BRANDING_NAME = "C&A Soluções em Copiadoras";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, branding } = useAuth();
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

  const isBrandingDefault =
    !branding ||
    !branding.display_name ||
    branding.display_name === DEFAULT_BRANDING_NAME ||
    (branding.partner_id === null && branding.client_id === null);

  return (
    <div className="login-page">
      <div className="login-container">
        {isBrandingDefault ? (
          <div style={{ textAlign: "center", marginBottom: "2rem" }}>
            <img
              src={DEFAULT_LOGO_URL}
              alt={DEFAULT_BRANDING_NAME}
              style={{
                width: "320px",
                height: "auto",
                borderRadius: "0",
                objectFit: "contain",
                maxWidth: "100%",
              }}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).src = DEFAULT_LOGO_URL;
              }}
            />
          </div>
        ) : (
          <div style={{ textAlign: "center", marginBottom: "2rem" }}>
            <img
              src={branding?.logo_src || DEFAULT_LOGO_URL}
              alt={branding?.display_name || DEFAULT_BRANDING_NAME}
              style={{
                width: "280px",
                height: "auto",
                objectFit: "contain",
                maxWidth: "100%",
                marginBottom: "1rem",
                background: "#fff",
                padding: 10,
                borderRadius: 10,
                border: "1px solid var(--border)",
              }}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).src = DEFAULT_LOGO_URL;
              }}
            />
            <h1 style={{ marginBottom: "0.5rem" }}>
              {branding?.display_name || DEFAULT_BRANDING_NAME}
            </h1>
            <p style={{ color: "var(--text-muted)" }}>
              {branding?.tagline || "Painel de Monitoramento de Impressoras"}
            </p>
          </div>
        )}

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
