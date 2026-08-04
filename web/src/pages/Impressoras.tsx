import { useEffect, useState } from "react";
import { api } from "../api";
import type { Printer } from "../types";
import { formatDateTimeBrasil, formatNumberBrasil } from "../utils";
import { useAuth } from "../context/AuthContext";

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
  const { user, loading: authLoading } = useAuth();
  const [printers, setPrinters] = useState<Printer[]>([]);

  const canManagePrinters =
    !authLoading && !!user && ["admin", "partner", "tech"].includes(user.role);

  const handleRemovePrinter = async (printer: Printer) => {
    const model = printer.model || printer.ip_address || "esta impressora";
    const ok = window.confirm(
      `Confirma REMOVER "${model}"?\n\n` +
        `Ela NÃO será mais monitorada e NÃO voltará a aparecer automaticamente, mesmo que seja encontrada na rede na próxima coleta.\n\n` +
        `(Se mudar de ideia depois, crie uma impressora manualmente com o mesmo IP/serial, ou contate o suporte.)`,
    );
    if (!ok) return;

    try {
      await api.ignorePrinter(printer.id);
      setPrinters((current) => current.filter((p) => p.id !== printer.id));
    } catch (e: any) {
      window.alert("Erro ao remover impressora: " + String(e?.message || e));
    }
  };

  useEffect(() => {
    if (authLoading || !user) return;
    api.getPrinters().then(setPrinters);
  }, [authLoading, user]);

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
                {canManagePrinters && <th style={{ width: 110 }}>Ações</th>}
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
                  <td>{formatNumberBrasil(p.pages_total)}</td>
                  <td><TonerBar level={p.toner_black} /></td>
                  <td>{formatDateTimeBrasil(p.last_seen)}</td>
                  {canManagePrinters && (
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{
                          color: "var(--danger)",
                          borderColor: "transparent",
                          background: "transparent",
                          padding: "0.3rem 0.6rem",
                          fontSize: 13,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                        title="Remover esta impressora do monitoramento"
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "rgba(239, 68, 68, 0.08)";
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "rgba(239, 68, 68, 0.3)";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "transparent";
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "transparent";
                        }}
                        onClick={() => handleRemovePrinter(p)}
                      >
                        🗑️ Remover
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
