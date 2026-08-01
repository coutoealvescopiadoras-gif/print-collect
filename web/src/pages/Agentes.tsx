import { useEffect, useState } from "react";
import { api } from "../api";
import type { Agent, Client } from "../types";
import { useAuth } from "../context/AuthContext";

export default function Agentes() {
  const { user } = useAuth();
  const effectiveRole = user?.role || "superadmin";
  const canManageAgents = effectiveRole === "superadmin" || effectiveRole === "partner_admin" || effectiveRole === "client_manager";
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [form, setForm] = useState({ client_id: 0, name: "" });
  const [downloadingAgentId, setDownloadingAgentId] = useState<number | null>(null);
  const [deletingAgentId, setDeletingAgentId] = useState<number | null>(null);

  const load = () => {
    api.getAgents().then(setAgents);
    api.getClients().then(setClients);
  };
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const agent = await api.createAgent(form.client_id, form.name);
    setNewToken(agent.api_token);
    setShowModal(false);
    setForm({ client_id: 0, name: "" });
    load();
  };

  const parseFilename = (contentDisposition: string) => {
    const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
    return match?.[1] || null;
  };

  const downloadWindowsPackage = async (agentId: number) => {
    try {
      setDownloadingAgentId(agentId);
      const { blob, contentDisposition } = await api.downloadAgentWindowsPackage(agentId);
      const filename = parseFilename(contentDisposition) || `print-collect-agent-windows-${agentId}.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloadingAgentId(null);
    }
  };

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
        {canManageAgents && (
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Novo agente</button>
        )}
      </div>

      <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem" }}>
        Baixe o pacote Windows do agente, extraia o ZIP e execute o arquivo "PrintCollectSetup.exe". O pacote já vai com a URL da API e o token preenchidos.
      </p>

      <div className="card">
        {agents.length === 0 ? (
          <div className="empty">Nenhum agente registrado</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>Cliente</th>
                <th>Último heartbeat</th>
                <th>Versão</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                      <span>{a.name}</span>
                      {canManageAgents && (
                        <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                          <button
                            className="btn btn-ghost"
                            onClick={() => downloadWindowsPackage(a.id)}
                            disabled={downloadingAgentId === a.id || deletingAgentId === a.id}
                          >
                            {downloadingAgentId === a.id ? "Baixando..." : "Baixar instalador"}
                          </button>
                          <button
                            className="btn btn-ghost"
                            onClick={() => deleteAgent(a.id, a.name)}
                            disabled={deletingAgentId === a.id || downloadingAgentId === a.id}
                            style={{ color: "var(--danger)" }}
                          >
                            {deletingAgentId === a.id ? "Excluindo..." : "Excluir"}
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                  <td>{clients.find((c) => c.id === a.client_id)?.name || `#${a.client_id}`}</td>
                  <td>
                    {a.last_heartbeat
                      ? new Date(a.last_heartbeat).toLocaleString("pt-BR")
                      : "Nunca"}
                  </td>
                  <td>{a.version || "—"}</td>
                  <td>
                    <span className={`badge ${a.active ? "online" : "offline"}`}>
                      {a.active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && canManageAgents && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Novo agente</h3>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "1rem" }}>
              Selecione o cliente e informe um nome para identificar onde este agente sera instalado, por exemplo:
              {' '}Agente Matriz, PC Recepcao ou Servidor Loja Centro.
            </p>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Cliente *</label>
                <select
                  required
                  value={form.client_id || ""}
                  onChange={(e) => setForm({ ...form, client_id: Number(e.target.value) })}
                  style={{ width: "100%", padding: "0.6rem", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
                >
                  <option value="">Selecione...</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Nome do agente / computador *</label>
                <input
                  required
                  placeholder="Ex: Agente Matriz, PC Recepcao ou Servidor Cliente"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary">Criar</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {newToken && (
        <div className="modal-overlay" onClick={() => setNewToken(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Token do agente</h3>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Este token já é incluído automaticamente no pacote baixado do agente. Guarde-o apenas para suporte, pois ele não será exibido novamente.
            </p>
            <div className="token-box">{newToken}</div>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => { navigator.clipboard.writeText(newToken); }}>
                Copiar
              </button>
              <button className="btn btn-ghost" onClick={() => setNewToken(null)}>Fechar</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
