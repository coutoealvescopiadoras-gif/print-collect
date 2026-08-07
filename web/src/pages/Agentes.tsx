import { useEffect, useState } from "react";
import { api } from "../api";
import type { Agent, Client } from "../types";
import { useAuth } from "../context/AuthContext";
import { formatDateTimeBrasil } from "../utils";

export default function Agentes() {
  const { user, loading: authLoading } = useAuth();
  const effectiveRole = user?.role || "superadmin";
  const canManageAgents = effectiveRole === "superadmin" || effectiveRole === "partner_admin" || effectiveRole === "client_manager";
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [deletingAgentId, setDeletingAgentId] = useState<number | null>(null);

  const load = () => {
    api.getAgents().then(setAgents);
    api.getClients().then(setClients);
  };
  useEffect(() => {
    if (authLoading || !user) return;
    load();
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

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Agentes</h1>
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
                <th>Último heartbeat</th>
                <th>Versão</th>
                <th>Status</th>
                {canManageAgents && <th style={{ width: "80px" }}>Ações</th>}
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{clients.find((c) => c.id === a.client_id)?.name || `#${a.client_id}`}</td>
                  <td>
                    {a.last_heartbeat
                      ? formatDateTimeBrasil(a.last_heartbeat)
                      : "Nunca"}
                  </td>
                  <td>{a.version || "—"}</td>
                  <td>
                    <span className={`badge ${a.active ? "online" : "offline"}`}>
                      {a.active ? "Ativo" : "Inativo"}
                    </span>
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
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
