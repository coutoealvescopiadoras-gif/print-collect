import { useEffect, useState } from "react";
import { api } from "../api";
import type { DashboardStats, Alert } from "../types";

const INSTALLER_DOWNLOAD_URL = "https://www.printcollect.com.br/PrintCollectSetup.exe";

function copyText(text: string) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => {
      window.prompt("Copie:", text);
    });
  } else {
    window.prompt("Copie:", text);
  }
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [copiedInstaller, setCopiedInstaller] = useState(false);

  useEffect(() => {
    Promise.all([api.getStats(), api.getAlerts(false)]).then(([s, a]) => {
      setStats(s);
      setAlerts(a.slice(0, 5));
    });
  }, []);

  if (!stats) return <div className="loading">Carregando...</div>;

  return (
    <>
      <h1 className="page-title">Dashboard</h1>

      {/* Card destaque: Download Instalador */}
      <div className="card" style={{ marginBottom: "1.25rem", padding: "1.1rem 1.25rem", background: "linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(16,185,129,0.12) 100%)", border: "1px solid rgba(59,130,246,0.3)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 380px", minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 16, marginBottom: "0.35rem", display: "flex", alignItems: "center", gap: "0.55rem" }}>
              💾 <span>Instalador Windows do Agente de Monitoramento</span>
            </div>
            <div style={{ fontSize: 13.5, color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Baixe o instalador oficial para instalar no computador dos seus clientes (ou no servidor de cada cliente). O instalador tem apenas 12,7 MB e já configura a inicialização automática com o Windows.
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
              <a
                href={INSTALLER_DOWNLOAD_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary"
                style={{ padding: "0.55rem 1rem", fontSize: 14, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
              >
                ⬇️ <span>Baixar PrintCollectSetup.exe</span>
              </a>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ padding: "0.55rem 1rem", fontSize: 14 }}
                onClick={() => {
                  copyText(INSTALLER_DOWNLOAD_URL);
                  setCopiedInstaller(true);
                  setTimeout(() => setCopiedInstaller(false), 2000);
                }}
              >
                {copiedInstaller ? "✓ Link copiado" : "📋 Copiar link de download"}
              </button>
              <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "'Courier New', ui-monospace, monospace" }}>
                {INSTALLER_DOWNLOAD_URL}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="label">Clientes ativos</div>
          <div className="value">{stats.total_clients}</div>
        </div>
        <div className="stat-card">
          <div className="label">Impressoras</div>
          <div className="value">{stats.total_printers}</div>
        </div>
        <div className="stat-card success">
          <div className="label">Online</div>
          <div className="value">{stats.online_printers}</div>
        </div>
        <div className="stat-card danger">
          <div className="label">Offline</div>
          <div className="value">{stats.offline_printers}</div>
        </div>
        <div className="stat-card warning">
          <div className="label">Alertas ativos</div>
          <div className="value">{stats.active_alerts}</div>
        </div>
        <div className="stat-card warning">
          <div className="label">Toner baixo</div>
          <div className="value">{stats.low_toner_count}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Alertas recentes</h2>
        </div>
        {alerts.length === 0 ? (
          <div className="empty">Nenhum alerta ativo</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Mensagem</th>
                <th>Severidade</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>{a.alert_type}</td>
                  <td>{a.message}</td>
                  <td>
                    <span className={`badge ${a.severity}`}>{a.severity}</span>
                  </td>
                  <td>{new Date(a.created_at).toLocaleString("pt-BR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
