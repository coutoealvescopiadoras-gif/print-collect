import { useEffect, useState } from "react";
import { resolveBaseUrl } from "../api";

type TestResult = {
  name: string;
  status: "pass" | "fail" | "info" | "running";
  output: string;
};

export default function Diagnostico() {
  const hostname = typeof window !== "undefined" ? window.location.hostname : "SSR";
  const protocol = typeof window !== "undefined" ? window.location.protocol : "https:";
  const envApiUrl = ((import.meta.env.VITE_API_URL as string | undefined) || "").trim();
  const envFallback = ((import.meta.env.VITE_API_URL_FALLBACK as string | undefined) || "").trim();
  const base = resolveBaseUrl();

  const [results, setResults] = useState<TestResult[]>([]);
  const [copied, setCopied] = useState(false);

  const addResult = (r: TestResult) => setResults((prev) => [...prev, r]);

  const run = async () => {
    setResults([]);

    addResult({ name: "01. Hostname atual", status: "info", output: hostname });
    addResult({ name: "02. Protocolo (http/https)", status: "info", output: protocol });
    addResult({ name: "03. import.meta.env.VITE_API_URL (vem do Vercel Painel / .env!)", status: envApiUrl ? "pass" : "fail", output: envApiUrl || "(VAZIO / nao configurado)" });
    addResult({ name: "04. import.meta.env.VITE_API_URL_FALLBACK", status: "info", output: envFallback || "(VAZIO)" });
    addResult({ name: "05. resolveBaseUrl() → valor USADO nas chamadas de API", status: base ? "pass" : "fail", output: base || "(VAZIO: vai usar /api/* relativo ao mesmo dominio!)" });

    const urlCorreta = "https://print-collect-api.onrender.com";
    const urlErradaSuspeita = "https://printcollect-api.onrender.com"; // sem hifen
    const baseMatchCorreta = base.toLowerCase() === urlCorreta.toLowerCase();
    addResult({
      name: "06. BaseURL coincide com RENDER esperado (COM HIFEN)?",
      status: baseMatchCorreta ? "pass" : "fail",
      output: baseMatchCorreta
        ? `SIM, URL CORRETA: ${urlCorreta}`
        : `NAO! Esperado='${urlCorreta}', OBTIDO='${base}'. Se estiver '${urlErradaSuspeita}' = URL SEM HIFEN (ERRADO). Se VAZIO = tentando usar Vercel Serverless.`,
    });

    const runFetchTest = async (label: string, fullUrl: string, opts: RequestInit = {}) => {
      const t0 = Date.now();
      try {
        const resp = await fetch(fullUrl, opts);
        const ms = Date.now() - t0;
        let body = "";
        try { body = (await resp.text()).slice(0, 500); } catch { body = "(nao conseguiu ler body)"; }
        addResult({
          name: label,
          status: resp.ok ? "pass" : "fail",
          output: `HTTP ${resp.status} ${resp.statusText} | ${ms}ms\nBody preview: ${body || "(vazio)"}`,
        });
        return resp.ok;
      } catch (err: any) {
        const ms = Date.now() - t0;
        const msg = String(err?.message || err || "Erro desconhecido fetch");
        let extra = "";
        if (msg.toLowerCase().includes("cors")) extra = "\n   >>> BLOQUEIO CORS!!!";
        else if (msg.toLowerCase().includes("network") || msg.toLowerCase().includes("dns") || msg.toLowerCase().includes("name or service")) extra = "\n   >>> FALHA REDE / DNS / URL NAO EXISTE!";
        else if (msg.toLowerCase().includes("failed to fetch")) extra = "\n   >>> CORS OU URL INACESSIVEL (verifique se existe / tem SSL)";
        addResult({
          name: label,
          status: "fail",
          output: `${msg} | ${ms}ms${extra}`,
        });
        return false;
      }
    };

    await runFetchTest("07. GET /health (URL resolvida)", base ? `${base}/health` : "/health");

    const corsHints: RequestInit = { method: "OPTIONS", headers: { Origin: `${protocol}//${hostname}`, "Access-Control-Request-Method": "POST" } };
    await runFetchTest("08. OPTIONS preflight /health (teste CORS real)", base ? `${base}/health` : "/health", corsHints);

    await runFetchTest("09. GET /health URL CERTA Render (COM HIFEM)", `${urlCorreta}/health`);
    await runFetchTest("10. OPTIONS preflight Render CERTO (COM HIFEM)", `${urlCorreta}/health`, corsHints);
    await runFetchTest("11. GET /health URL ERRADA (SEM HIFEM) - deve falhar", `${urlErradaSuspeita}/health`);

    const userMsg = encodeURIComponent("opa");
    await runFetchTest("12. POST /api/token (credenciais invalidas intencionalmente para testar rota)",
      base ? `${base}/api/token?username=teste&password=teste&grant_type=password` : `/api/token?username=teste&password=teste&grant_type=password`,
      { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: `username=diag_${userMsg}&password=xxx&grant_type=password` },
    );

    addResult({
      name: "13. FIM / RESUMO",
      status: "info",
      output:
        (baseMatchCorreta ? "✅ URL CORRETA" : "❌ URL ERRADA OU VAZIA") +
        " | Copie o relatorio inteiro e envie para o suporte tecnico!",
    });
  };

  useEffect(() => { run(); }, []);

  const fullReport = () => {
    const header = [
      "==================== RELATORIO DIAGNOSTICO PRINTCOLLECT ====================",
      `Data: ${new Date().toLocaleString("pt-BR")}`,
      `Hostname: ${hostname} | Protocolo: ${protocol}`,
      "=============================================================================",
    ].join("\n");
    const lines = results.map((r) => {
      const simb = r.status === "pass" ? "[OK ]" : r.status === "fail" ? "[ERR]" : "[INF]";
      return `${simb} ${r.name}\n      ${r.output.split("\n").join("\n      ")}`;
    }).join("\n\n");
    return `${header}\n\n${lines}\n`;
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullReport());
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      alert("Nao foi possivel copiar. Selecione e copie manualmente abaixo:");
    }
  };

  const bg = (s: TestResult["status"]) =>
    s === "pass" ? "#065f46" : s === "fail" ? "#991b1b" : s === "running" ? "#854d0e" : "#1e3a8a";

  return (
    <div style={{
      minHeight: "100vh", background: "#0f172a", color: "#e5e7eb",
      fontFamily: "system-ui, sans-serif", padding: "2rem 1rem",
    }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        <h1 style={{ fontSize: "1.75rem", margin: 0, marginBottom: "0.25rem" }}>🔧 Diagnóstico Rápido Login PrintCollect</h1>
        <p style={{ color: "#94a3b8", margin: "0 0 1rem 0" }}>
          Copie todo o relatório abaixo e envie para o suporte técnico.
        </p>

        <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
          <button onClick={run} style={{
            background: "#2563eb", color: "#fff", padding: "0.6rem 1.2rem",
            border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600,
          }}>🔄 Rodar Novamente</button>
          <button onClick={copy} style={{
            background: copied ? "#059669" : "#0ea5e9", color: "#fff", padding: "0.6rem 1.2rem",
            border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600,
          }}>{copied ? "✅ Copiado!" : "📋 Copiar Relatorio"}</button>
        </div>

        <div style={{
          background: "#020617", padding: "1rem", borderRadius: 8,
          border: "1px solid #1e293b", fontSize: 13, lineHeight: 1.45, overflow: "auto",
          whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "ui-monospace, monospace",
        }}>{fullReport()}</div>

        <div style={{ marginTop: "1.5rem" }}>
          {results.map((r, i) => (
            <div key={i} style={{
              marginBottom: "0.5rem", padding: "0.55rem 0.75rem", borderRadius: 6,
              borderLeft: `6px solid ${bg(r.status)}`, background: "#1e293b",
            }}>
              <div style={{ fontWeight: 700, fontSize: 14, display: "flex", justifyContent: "space-between" }}>
                <span>{r.name}</span>
                <span style={{
                  color: "#fff", background: bg(r.status), padding: "0.12rem 0.55rem",
                  borderRadius: 999, fontSize: 11, fontWeight: 700,
                }}>{r.status.toUpperCase()}</span>
              </div>
              <pre style={{ margin: "0.35rem 0 0 0", whiteSpace: "pre-wrap", fontSize: 12, color: "#cbd5e1", fontFamily: "ui-monospace, monospace" }}>{r.output}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
