import { useEffect, useState } from "react";
import { api } from "../api";
import type { Client } from "../types";

export default function Clientes() {
  const [clients, setClients] = useState<Client[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: "", cnpj: "", contact_name: "", contact_email: "" });

  const load = () => api.getClients().then(setClients);
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.createClient(form);
    setShowModal(false);
    setForm({ name: "", cnpj: "", contact_name: "", contact_email: "" });
    load();
  };

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Clientes</h1>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Novo cliente</button>
      </div>

      <div className="card">
        {clients.length === 0 ? (
          <div className="empty">Nenhum cliente cadastrado</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>CNPJ</th>
                <th>Contato</th>
                <th>E-mail</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.cnpj || "—"}</td>
                  <td>{c.contact_name || "—"}</td>
                  <td>{c.contact_email || "—"}</td>
                  <td>
                    <span className={`badge ${c.active ? "online" : "offline"}`}>
                      {c.active ? "Ativo" : "Inativo"}
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
            <h3>Novo cliente</h3>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Nome *</label>
                <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="form-group">
                <label>CNPJ</label>
                <input value={form.cnpj} onChange={(e) => setForm({ ...form, cnpj: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Contato</label>
                <input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
              </div>
              <div className="form-group">
                <label>E-mail</label>
                <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary">Salvar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
