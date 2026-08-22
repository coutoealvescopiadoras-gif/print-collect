import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { PRINT_COLLECT_LOGO } from "../assets/placeholder-logo";
import { resolveBaseUrl } from "../api";

const DEBUG_STORAGE_KEY = "pc_debug_api_url";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  // ================= MENU DEBUG SECRETO: 7 cliques no LOGO PrintCollect!
  const [logoClicks, setLogoClicks] = useState(0);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugUrl, setDebugUrl] = useState<string>("");
  const [debugResult, setDebugResult] = useState<string>("");
  const [debugRunning, setDebugRunning] = useState(false);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(DEBUG_STORAGE_KEY) || "";
      if (saved) setDebugUrl(saved);
    } catch { /* noop */ }
  }, []);

  const clickLogo = () => {
    const next = logoClicks + 1;
    if (next >= 7) {
      setDebugOpen((d) => !d);
      setLogoClicks(0);
      return;
    }
    setLogoClicks(next);
    setTimeout(() => setLogoClicks(0), 4000);
  };

  const debugSave = (url: string) => {
    const cleaned = url.trim().replace(/\/$/, "");
    window.localStorage.setItem(DEBUG_STORAGE_KEY, cleaned);
    window.location.reload();
  };

  const debugClear = () => {
    window.localStorage.removeItem(DEBUG_STORAGE_KEY);
    window.location.reload();
  };

  const runDebugTest = async (base: string) => {
    setDebugRunning(true);
    setDebugResult("");
    const lines: string[] = [];
    const url0 = performance.now();

    const doOne = async (label: string, path: string, init: RequestInit = {}) => {
      const full = base ? base + path : path;
      lines.push("-> " + label + " " + full);
      const t1 = performance.now();
      try {
        const resp = await fetch(full, init);
        const ms = Math.round(performance.now() - t1);
        let bodyText = "";
        try { bodyText = (await resp.text()).slice(0, 800); } catch { bodyText = "(sem body)"; }
        lines.push("   HTTP " + resp.status + " " + resp.statusText + " | " + ms + "ms");
        if (bodyText) {
          try {
            const j = JSON.parse(bodyText);
            lines.push("   json: " + JSON.stringify(j));
            return resp.ok;
          } catch {
            lines.push("   texto: " + bodyText);
            return resp.ok;
          }
        }
        return resp.ok;
      } catch (e: any) {
        const ms = Math.round(performance.now() - t1);
        const m = String(e?.message || String(e));
        lines.push("   FAIL " + ms + "ms: " + m);
        if (m.toLowerCase().includes("cors")) lines.push("      >>> BLOQUEIO CORS!");
        else if (m.toLowerCase().includes("failed to fetch")) lines.push("      >>> URL INACESSIVEL (verifique se a API esta UP)");
        return false;
      }
    };

    lines.push("--- DEBUG " + new Date().toLocaleString("pt-BR") + " ---");
    lines.push("Base escolhida: " + (base || "(VAZIA = /api/* do MESMO dominio VERCEL)"));

    const optsGet: RequestInit = { method: "OPTIONS", headers: { Origin: window.location.origin, "Access-Control-Request-Method": "GET" } };
    const optsPost: RequestInit = { method: "OPTIONS", headers: { Origin: window.location.origin, "Access-Control-Request-Method": "POST" } };
    await doOne("1/4 OPTIONS preflight /health", "/health", optsGet);
    const okH = await doOne("2/4 GET /health", "/health");
    const okD = await doOne("3/4 GET /debug-init (inicializacao)", "/debug-init");
    await doOne("4/4 OPTIONS /api/token (rota login)", "/api/token", optsPost);

    const total = Math.round(performance.now() - url0);
    lines.push("");
    lines.push("=== RESUMO (" + total + "ms) /health=" + (okH ? "OK" : "FAIL") + " /debug-init=" + (okD ? "OK" : "FAIL"));
    if (!okH && !okD) lines.push("!! Backend NAO esta respondendo NENHUM teste.");
    if (okH && !okD) lines.push("!! /health OK mas /debug-init FAIL = backend esta desatualizado (build antigo ainda).");

    setDebugResult(lines.join("\n"));
    setDebugRunning(false);
  };

  const currentFallback = resolveBaseUrl() || "(VAZIA → /api/* do MESMO dominio VERCEL)";
  const savedOverride = debugUrl.trim() || "(nenhum URL salva)";

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
            title={debugOpen ? "Menu debug aberto. Clique 7x novamente para fechar ou no botão X." : "Clique 7x rapidamente para abrir o MENU DEBUG DE SUPORTE TECNICO"}
            onClick={clickLogo}
            style={{
              width: "380px",
              height: "auto",
              borderRadius: "0",
              objectFit: "contain",
              maxWidth: "100%",
              cursor: "pointer",
              border: logoClicks > 0 ? "3px dashed #facc15" : "none",
              padding: logoClicks > 0 ? "6px" : "0",
            }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).src = PRINT_COLLECT_LOGO;
            }}
          />
          {logoClicks > 0 && logoClicks < 7 && (
            <div style={{ color: "#facc15", marginTop: "0.5rem", fontSize: "13px", fontWeight: 700 }}>
              {7 - logoClicks} clique{7 - logoClicks === 1 ? "" : "s"} para abrir MENU DEBUG SUPORTE...
            </div>
          )}
          <p style={{ color: "var(--text-muted)", fontSize: "0.95rem", marginTop: "0.75rem", marginBottom: 0 }}>
            Painel de Monitoramento Automático de Contadores de Impressoras
          </p>
        </div>

        {debugOpen && (
          <div style={{
            marginBottom: "1.5rem", padding: "1rem 1.25rem",
            borderRadius: "14px", border: "2px solid #38bdf8",
            background: "#0c4a6e", color: "#e0f2fe",
            textAlign: "left", fontSize: "13px", fontFamily: "ui-monospace, monospace",
          }}>
            <div style={{ fontWeight: 700, marginBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
              <span>🔧 MENU DEBUG SUPORTE TÉCNICO — URL da API (Prioridade TOTAL)</span>
              <button type="button" onClick={() => setDebugOpen(false)} style={{
                border: "1px solid #fff", background: "transparent", color: "#fff",
                padding: "0.15rem 0.85rem", borderRadius: 6, cursor: "pointer", fontSize: 12,
              }}>X FECHAR</button>
            </div>

            <div style={{ marginBottom: "1rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
              <div>✅ Resolvido AGORA (getApiBaseUrl): <b style={{ color: "#fcd34d" }}>{currentFallback}</b></div>
              <div>💾 Salvo em localStorage (sobrescreve TUDO!): <b style={{ color: "#86efac" }}>{savedOverride}</b></div>
              <div>🌐 Página rodando em: <b>{window.location.origin}</b></div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <label style={{ fontWeight: 700, fontSize: "13px" }}>
                Digite a URL da API (deixe VAZIO = padrão: /api/* do MESMO domínio Vercel):
              </label>
              <input
                type="text"
                value={debugUrl}
                onChange={(e) => setDebugUrl(e.target.value)}
                placeholder="ex: https://print-collect-api.onrender.com  OU  deixe vazio  OU  http://localhost:8000"
                style={{ padding: "0.55rem 0.85rem", borderRadius: 8, border: "1px solid #0ea5e9", background: "#0b2b47", color: "#fff", fontSize: 13, fontFamily: "ui-monospace, monospace" }}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginTop: "0.1rem" }}>
                <button type="button" onClick={() => setDebugUrl("")} style={{ padding: "0.35rem 0.8rem", background: "#475569", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
                  ⚙️ Padrão (VAZIO = Vercel /api/*)
                </button>
                <button type="button" onClick={() => setDebugUrl("https://print-collect-api.onrender.com")} style={{ padding: "0.35rem 0.8rem", background: "#0f766e", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
                  🟢 Render (COM hífen)
                </button>
                <button type="button" onClick={() => setDebugUrl("https://printcollect-api.onrender.com")} style={{ padding: "0.35rem 0.8rem", background: "#7c3aed", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
                  🟣 Render (SEM hífen)
                </button>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.35rem" }}>
                <button
                  type="button"
                  disabled={debugRunning}
                  onClick={() => runDebugTest(debugUrl.trim().replace(/\/$/, ""))}
                  style={{ padding: "0.55rem 1rem", background: "#0ea5e9", color: "#fff", border: "none", borderRadius: 8, cursor: debugRunning ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 700 }}
                >
                  {debugRunning ? "⏳ Executando..." : "🧪 TESTAR Conexao (4 endpoints)"}
                </button>
                <button
                  type="button"
                  onClick={() => debugSave(debugUrl)}
                  style={{ padding: "0.55rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 700 }}
                >💾 SALVAR e recarregar (aplica!)
                </button>
                <button
                  type="button"
                  onClick={debugClear}
                  style={{ padding: "0.55rem 1rem", background: "#dc2626", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 700 }}
                >🗑️ APAGAR URL salva (default)
                </button>
              </div>

              {debugResult && (
                <pre style={{
                  marginTop: "0.5rem", padding: "0.85rem 1rem",
                  background: "#020617", color: "#bae6fd",
                  borderRadius: 8, fontSize: "12px",
                  border: "1px solid #0ea5e9",
                  whiteSpace: "pre-wrap", wordBreak: "break-word",
                  fontFamily: "ui-monospace, monospace", maxHeight: 260, overflowY: "auto",
                }}>
                  {debugResult}
                </pre>
              )}
            </div>
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
