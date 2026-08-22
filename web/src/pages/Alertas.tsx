import { useEffect, useState } from "react";
import { api } from "../api";
import type { Alert } from "../types";
import { formatDateTimeBrasil } from "../utils";
import { useAuth } from "../context/AuthContext";

export default function Alertas() {
  const { user, loading: authLoading } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);

  const load = () =>
    api.getAlerts(false).then((r) => {
      setAlerts(r);
      setLastRefreshAt(new Date());
    });
  useEffect(() => {
    if (authLoading || !user) return;
    load();
  }, [authLoading, user]);

  useEffect(() => {
    if (authLoading || !user) return;
    const id = window.setInterval(() => {
      load();
    }, 60000);
    return () => window.clearInterval(id);
  }, [authLoading, user]);

  const handleResolve = async (id: number) => {
    await api.resolveAlert(id);
    load();
  };

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "1rem",
          marginBottom: "1rem",
        }}
      >
        <h1 className="page-title" style={{ marginBottom: 0 }}>
          Alertas
        </h1>
        {lastRefreshAt && (
          <div
            style={{
              fontSize: "0.8rem",
              color: "var(--text-muted)",
              padding: "0.35rem 0.7rem",
              borderRadius: 999,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
            }}
          >
            <span style={{ color: "var(--success)" }}>●</span>
            Atualizado em {formatDateTimeBrasil(lastRefreshAt)}
          </div>
        )}
      </div>

      <div className="card">
        {alerts.length === 0 ? (
          <div className="empty">Nenhum alerta ativo</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Impressora</th>
                <th>Serial</th>
                <th>IP</th>
                <th>Tipo</th>
                <th>Mensagem</th>
                <th>Severidade</th>
                <th>Data</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.client_name ? (
                      <strong>{a.client_name}</strong>
                    ) : (
                      <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                        #{a.client_id ?? "—"}
                      </span>
                    )}
                  </td>
                  <td>
                    {a.printer_model ? (
                      <div>
                        <div>
                          <strong>{a.printer_model}</strong>
                        </div>
                        <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                          {a.printer_manufacturer ? a.printer_manufacturer : ""}
                        </div>
                      </div>
                    ) : (
                      <span>
                      <div>#{a.printer_id}</div>
                        <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                          (modelo não cadastrado)
                        </span>
                    </span>
                    )}
                  </td>
                  <td>
                    {a.printer_serial ? (
                      <code style={{ fontSize: "0.85rem" }}>{a.printer_serial}</code>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td>
                    {a.printer_ip ? (
                      <code style={{ fontSize: "0.85rem" }}>{a.printer_ip}</code>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td>{a.alert_type}</td>
                  <td>{a.message}</td>
                  <td>
                    <span className={`badge ${a.severity}`}>{a.severity}</span>
                  </td>
                  <td>{formatDateTimeBrasil(a.created_at)}</td>
                  <td>
                    <button className="btn btn-ghost" onClick={() => handleResolve(a.id)}>
                      Resolver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
