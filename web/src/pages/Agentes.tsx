import { useEffect, useState } from "react";
import { api } from "../api";
import type { Agent, Client } from "../types";

export default function Agentes() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [form, setForm] = useState({ client_id: 0, name: "" });

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

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Agentes</h1>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Novo agente</button>
      </div>

      <p style={{ color: "var(--text-muted)", marginBottom: "1.5rem" }}>
        Instale o agente no PC ou servidor do cliente. Ele faz varredura SNMP na rede local e envia os dados automaticamente.
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
                  <td>{a.name}</td>
                  <td>#{a.client_id}</td>
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

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Novo agente</h3>
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
                <label>Nome do agente *</label>
                <input required placeholder="Ex: Agente Matriz" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
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
              Copie este token para o arquivo <code>agent/config.yaml</code>. Ele não será exibido novamente.
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
