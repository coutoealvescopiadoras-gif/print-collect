import { useEffect, useState } from "react";
import { api } from "../api";
import type { Agent, Client, Printer } from "../types";
import { useAuth } from "../context/AuthContext";
import { formatDateTimeBrasil } from "../utils";

function getAgentInactiveInfo(agent: Agent): { days: number; hours: number; totalHours: number } | null {
  if (!agent.last_heartbeat) return { days: 9999, hours: 0, totalHours: 999999 };
  try {
    const last = new Date(agent.last_heartbeat).getTime();
    if (isNaN(last)) return { days: 9999, hours: 0, totalHours: 999999 };
    const diff = Date.now() - last;
    if (diff < 0) return null;
    const totalHours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(totalHours / 24);
    const hours = totalHours - days * 24;
    return { days, hours, totalHours };
  } catch {
    return null;
  }
}

export default function Agentes() {
  const { user, loading: authLoading } = useAuth();
  const effectiveRole = user?.role || "superadmin";
  const canManageAgents = effectiveRole === "superadmin" || effectiveRole === "partner_admin" || effectiveRole === "client_manager";
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [deletingAgentId, setDeletingAgentId] = useState<number | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);

  const load = () => {
    Promise.all([api.getAgents(), api.getClients(), api.getPrinters()]).then(([a, c, p]) => {
      setAgents(a);
      setClients(c);
      setPrinters(p || []);
      setLastRefreshAt(new Date());
    });
  };
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

  const deleteAgent = async (agentId: number, agentName: string) => {
    const ok = window.confirm(`Excluir o agente "${agentName}"?\n\nO token deixa de funcionar imediatamente.`);
    if (!ok) return;
    try {
      setDeletingAgentId(agentId);
      await api.deleteAgent(agentId);
      load();
    } finally {
      setDeletingAgentId(null);
    }
  };

  const printerCountByClient = new Map<number, number>();
  for (const p of printers) {
    if (p.ignored) continue;
    const cid = p.client_id;
    if (!cid) continue;
    printerCountByClient.set(cid, (printerCountByClient.get(cid) || 0) + 1);
  }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", gap: "0.75rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Agentes</h1>
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

      <div className="card" style={{ padding: "1rem 1.25rem", marginBottom: "1.5rem", background: "var(--bg-soft)", borderLeft: "4px solid var(--primary)" }}>
        <p style={{ color: "var(--text)", marginBottom: "0.25rem", fontWeight: 600 }}>
          💡 Como os agentes são criados?
        </p>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", margin: 0 }}>
          <strong>NÃO há necessidade de criar agentes manualmente aqui.</strong> Basta cadastrar o cliente no menu
          {' '}<strong>Clientes</strong>, copiar o <strong>código do cliente</strong> (8 caracteres), baixar o instalador
          no menu <strong>Instalador</strong> e digitar o código na tela preta ao final da instalação.
          O agente é criado <strong>automaticamente</strong> no sistema ao concluir o pareamento.
        </p>
      </div>

      <div className="card">
        {agents.length === 0 ? (
          <div className="empty">Nenhum agente registrado ainda — instale o agente em um cliente para ele aparecer aqui.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>Cliente</th>
                <th style={{ width: 110, textAlign: "center" }}>🖨️ Impressoras</th>
                <th>Último heartbeat</th>
                <th>Versão</th>
                <th style={{ width: 170 }}>Status</th>
                {canManageAgents && <th style={{ width: "80px" }}>Ações</th>}
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => {
                const inactive = getAgentInactiveInfo(a);
                const isInactive24h = !!inactive && inactive.totalHours >= 24;
                const isCritical = !!inactive && inactive.totalHours >= 72;
                const totalPrinters = printerCountByClient.get(a.client_id) || 0;
                return (
                  <tr
                    key={a.id}
                    style={isCritical ? { background: "rgba(220, 53, 69, 0.08)" } : isInactive24h ? { background: "rgba(253, 126, 20, 0.08)" } : undefined}
                  >
                    <td style={isCritical ? { fontWeight: 600, color: "var(--danger)" } : undefined}>{a.name}</td>
                    <td>{clients.find((c) => c.id === a.client_id)?.name || `#${a.client_id}`}</td>
                    <td style={{ textAlign: "center", fontWeight: 600 }}>
                      {totalPrinters > 0 ? totalPrinters : <span style={{ color: "var(--text-muted)" }}>0</span>}
                    </td>
                    <td>
                      {a.last_heartbeat
                        ? formatDateTimeBrasil(a.last_heartbeat)
                        : <span style={{ color: "var(--text-muted)" }}>Nunca</span>}
                    </td>
                    <td>{a.version || <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                    <td>
                      {isInactive24h ? (
                        <span className={`badge ${isCritical ? "offline" : "warning"}`} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                          {isCritical ? "🔴" : "🟠"}
                          {inactive && inactive.days > 0
                            ? `Inativo há ${inactive.days}d ${inactive.hours}h`
                            : inactive && inactive.hours > 0
                              ? `Inativo há ${inactive.hours}h`
                              : `Inativo há >24h`}
                        </span>
                      ) : (
                        <span className={`badge ${a.active ? "online" : "offline"}`}>
                          {a.active ? "Ativo" : "Inativo"}
                        </span>
                      )}
                    </td>
                    {canManageAgents && (
                      <td>
                        <button
                          className="btn btn-ghost"
                          onClick={() => deleteAgent(a.id, a.name)}
                          disabled={deletingAgentId === a.id}
                          style={{ color: "var(--danger)", padding: "0.35rem 0.6rem" }}
                        >
                          {deletingAgentId === a.id ? "Excluindo..." : "Excluir"}
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
