import { useEffect, useState } from "react";
import { api } from "../api";
import type { Printer } from "../types";

function TonerBar({ level }: { level: number | null }) {
  if (level === null) return <span>—</span>;
  const cls = level <= 5 ? "critical" : level <= 15 ? "low" : "ok";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <div className="toner-bar">
        <div className={`toner-bar-fill ${cls}`} style={{ width: `${level}%` }} />
      </div>
      <span style={{ fontSize: "0.8rem" }}>{level}%</span>
    </div>
  );
}

export default function Impressoras() {
  const [printers, setPrinters] = useState<Printer[]>([]);

  useEffect(() => {
    api.getPrinters().then(setPrinters);
  }, []);

  return (
    <>
      <h1 className="page-title">Impressoras</h1>

      <div className="card">
        {printers.length === 0 ? (
          <div className="empty">Nenhuma impressora registrada. Instale um agente no cliente para coleta automática.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Modelo</th>
                <th>IP</th>
                <th>Serial</th>
                <th>Status</th>
                <th>Páginas</th>
                <th>Toner</th>
                <th>Última coleta</th>
              </tr>
            </thead>
            <tbody>
              {printers.map((p) => (
                <tr key={p.id}>
                  <td>
                    <div>{p.model || "—"}</div>
                    {p.manufacturer && <small style={{ color: "var(--text-muted)" }}>{p.manufacturer}</small>}
                  </td>
                  <td>{p.ip_address}</td>
                  <td>{p.serial_number || "—"}</td>
                  <td>
                    <span className={`badge ${p.status}`}>{p.status}</span>
                  </td>
                  <td>{p.pages_total.toLocaleString("pt-BR")}</td>
                  <td><TonerBar level={p.toner_black} /></td>
                  <td>
                    {p.last_seen
                      ? new Date(p.last_seen).toLocaleString("pt-BR")
                      : "—"}
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
