import { useEffect, useState } from "react";
import { api } from "../api";
import type { DashboardStats, Alert } from "../types";
import { formatDateTimeBrasil } from "../utils";
import { useAuth } from "../context/AuthContext";

export default function Dashboard() {
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    if (authLoading || !user) return;
    Promise.all([api.getStats(), api.getAlerts(false)]).then(([s, a]) => {
      setStats(s);
      setAlerts(a.slice(0, 5));
    });
  }, [authLoading, user]);

  if (!stats) return <div className="loading">Carregando...</div>;

  return (
    <>
      <h1 className="page-title">Dashboard</h1>

      <div
        style={{
          display: "flex",
          flexDirection: "row",
          flexWrap: "wrap",
          justifyContent: "flex-start",
          alignItems: "stretch",
          gap: "1rem",
          marginBottom: "2rem",
          width: "100%",
          maxWidth: "100%",
          boxSizing: "border-box",
          clear: "both",
          float: "none",
          padding: 0,
          margin: 0,
          marginBottom: "2rem",
        }}
      >
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.25rem",
            boxSizing: "border-box",
            minWidth: "170px",
            width: "auto",
            flex: "1 1 calc(25% - 1rem)",
            maxWidth: "calc(25% - 1rem)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Clientes ativos
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700 }}>{stats.total_clients}</div>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.25rem",
            boxSizing: "border-box",
            minWidth: "170px",
            width: "auto",
            flex: "1 1 calc(25% - 1rem)",
            maxWidth: "calc(25% - 1rem)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Impressoras
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700 }}>{stats.total_printers}</div>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.25rem",
            boxSizing: "border-box",
            minWidth: "170px",
            width: "auto",
            flex: "1 1 calc(25% - 1rem)",
            maxWidth: "calc(25% - 1rem)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Online
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--success)" }}>{stats.online_printers}</div>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.25rem",
            boxSizing: "border-box",
            minWidth: "170px",
            width: "auto",
            flex: "1 1 calc(25% - 1rem)",
            maxWidth: "calc(25% - 1rem)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Offline
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--danger)" }}>{stats.offline_printers}</div>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.25rem",
            boxSizing: "border-box",
            minWidth: "170px",
            width: "auto",
            flex: "1 1 calc(25% - 1rem)",
            maxWidth: "calc(25% - 1rem)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Alertas ativos
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--warning)" }}>{stats.active_alerts}</div>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: "1.25rem",
            boxSizing: "border-box",
            minWidth: "170px",
            width: "auto",
            flex: "1 1 calc(25% - 1rem)",
            maxWidth: "calc(25% - 1rem)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Toner baixo
          </div>
          <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--warning)" }}>{stats.low_toner_count}</div>
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
                  <td>{formatDateTimeBrasil(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
