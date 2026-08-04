import { useEffect, useState } from "react";
import { api } from "../api";
import type { Alert } from "../types";
import { formatDateTimeBrasil } from "../utils";

export default function Alertas() {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const load = () => api.getAlerts(false).then(setAlerts);
  useEffect(() => { load(); }, []);

  const handleResolve = async (id: number) => {
    await api.resolveAlert(id);
    load();
  };

  return (
    <>
      <h1 className="page-title">Alertas</h1>

      <div className="card">
        {alerts.length === 0 ? (
          <div className="empty">Nenhum alerta ativo</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Impressora</th>
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
                  <td>#{a.printer_id}</td>
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
