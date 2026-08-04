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
