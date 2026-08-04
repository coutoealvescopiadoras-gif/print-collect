import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";
import type { Client, Partner, User } from "../types";

const ROLE_OPTIONS = [
  { value: "superadmin", label: "Superadmin" },
  { value: "partner_admin", label: "Revendedor" },
  { value: "client_manager", label: "Gestor do cliente" },
  { value: "client_viewer", label: "Cliente" },
] as const;

export default function Usuarios() {
  const { user: currentUser, loading: authLoading } = useAuth();
  const effectiveRole = currentUser?.role || "superadmin";
  const isSuperadmin = effectiveRole === "superadmin";
  const isPartnerAdmin = effectiveRole === "partner_admin";
  const canManageUsers = isSuperadmin || isPartnerAdmin || effectiveRole === "client_manager";
  const [users, setUsers] = useState<User[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resettingPassword, setResettingPassword] = useState(false);
  const [error, setError] = useState("");
  const [resetError, setResetError] = useState("");
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [form, setForm] = useState({
    email: "",
    password: "",
    role: "client_viewer" as User["role"],
    client_id: currentUser?.client_id || 0,
    partner_id: currentUser?.partner_id || 0,
  });

  const load = async () => {
    const [usersData, clientsData, partnersData] = await Promise.all([
      api.getUsers(),
      api.getClients(),
      isSuperadmin ? api.getPartners() : Promise.resolve([]),
    ]);
    setUsers(usersData);
    setClients(clientsData);
    setPartners(partnersData);
  };

  useEffect(() => {
    if (authLoading || !currentUser || !canManageUsers) return;
    load();
  }, [authLoading, currentUser, canManageUsers]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.createUser({
        email: form.email,
        password: form.password,
        role: form.role,
        client_id: form.role === "superadmin" || form.role === "partner_admin" ? null : form.client_id || currentUser?.client_id || null,
        partner_id: form.role === "partner_admin" ? (isSuperadmin ? (form.partner_id || null) : (currentUser?.partner_id || null)) : null,
      });
      setShowModal(false);
      setForm({
        email: "",
        password: "",
        role: "client_viewer",
        client_id: currentUser?.client_id || 0,
        partner_id: currentUser?.partner_id || 0,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar usuário");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (item: User) => {
    await api.updateUser(item.id, { active: !item.active });
    await load();
  };

  const handleDelete = async (item: User) => {
    const confirm1 = window.confirm(
      `⚠️ EXCLUIR USUÁRIO PERMANENTEMENTE?\n\nLogin: ${item.email}\nPerfil: ${ROLE_OPTIONS.find((r) => r.value === item.role)?.label || item.role}\n\n📢 ESTA AÇÃO NÃO PODE SER DESFEITA!`
    );
    if (!confirm1) return;
    const confirm2 = window.confirm(
      `✅ ÚLTIMA CONFIRMAÇÃO:\n\nTem CERTEZA ABSOLUTA que quer apagar "${item.email}"?\n\nTodos os acessos deste login serão removidos IMEDIATAMENTE.`
    );
    if (!confirm2) return;
    try {
      await api.deleteUser(item.id);
      await load();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Erro ao excluir usuário. Verifique as permissões.");
    }
  };

  const openResetModal = (item: User) => {
    setSelectedUser(item);
    setResetPassword("");
    setResetError("");
    setShowResetModal(true);
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    if (resetPassword.length < 6) {
      setResetError("A nova senha deve ter pelo menos 6 caracteres.");
      return;
    }
    try {
      setResettingPassword(true);
      setResetError("");
      await api.updateUser(selectedUser.id, { password: resetPassword });
      setShowResetModal(false);
      setSelectedUser(null);
      setResetPassword("");
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "Erro ao redefinir senha");
    } finally {
      setResettingPassword(false);
    }
  };

  if (!canManageUsers) {
    return (
      <>
        <h1 className="page-title">Usuários</h1>
        <div className="card">
          <div className="empty">Você não tem permissão para gerenciar usuários.</div>
        </div>
      </>
    );
  }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Usuários</h1>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Novo usuário</button>
      </div>

      <div className="card">
        {users.length === 0 ? (
          <div className="empty">Nenhum usuário cadastrado</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Login</th>
                <th>E-mail</th>
                <th>Perfil</th>
                <th>Cliente</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id}>
                  <td>{item.email}</td>
                  <td>{item.email}</td>
                  <td>{ROLE_OPTIONS.find((role) => role.value === item.role)?.label || item.role}</td>
                  <td>{clients.find((client) => client.id === item.client_id)?.name || (item.client_id ? `#${item.client_id}` : "—")}</td>
                  <td>
                    <span className={`badge ${item.active ? "online" : "offline"}`}>
                      {item.active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                      {isSuperadmin && item.id !== currentUser?.id && (
                        <button className="btn btn-ghost" onClick={() => openResetModal(item)}>
                          Resetar senha
                        </button>
                      )}
                      {item.id !== currentUser?.id && (
                        <button className="btn btn-ghost" onClick={() => toggleActive(item)}>
                          {item.active ? "Desativar" : "Ativar"}
                        </button>
                      )}
                      {item.id !== currentUser?.id && (
                        <button
                          className="btn btn-ghost"
                          style={{
                            border: "1px solid var(--danger)",
                            color: "var(--danger)",
                            background: "rgba(220, 38, 38, 0.06)",
                            fontWeight: 600,
                          }}
                          onClick={() => handleDelete(item)}
                          title="Excluir usuário permanentemente"
                        >
                          🗑️ Excluir
                        </button>
                      )}
                    </div>
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
            <h3>Novo usuário</h3>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>E-mail / Login *</label>
                <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Senha *</label>
                <input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Perfil *</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}
                  style={{ width: "100%", padding: "0.6rem", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
                >
                  {ROLE_OPTIONS.filter((role) => {
                    if (isSuperadmin) return true;
                    if (isPartnerAdmin) return role.value !== "superadmin";
                    return role.value === "client_manager" || role.value === "client_viewer";
                  }).map((role) => (
                    <option key={role.value} value={role.value}>{role.label}</option>
                  ))}
                </select>
              </div>
              {isSuperadmin && form.role === "partner_admin" && (
                <div className="form-group">
                  <label>Revendedor *</label>
                  <select
                    required
                    value={form.partner_id || ""}
                    onChange={(e) => setForm({ ...form, partner_id: Number(e.target.value) })}
                    style={{ width: "100%", padding: "0.6rem", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
                  >
                    <option value="">Selecione...</option>
                    {partners.map((partner) => (
                      <option key={partner.id} value={partner.id}>{partner.name}</option>
                    ))}
                  </select>
                </div>
              )}
              {form.role !== "superadmin" && form.role !== "partner_admin" && (
                <div className="form-group">
                  <label>Cliente *</label>
                  <select
                    required
                    value={form.client_id || ""}
                    onChange={(e) => setForm({ ...form, client_id: Number(e.target.value) })}
                    disabled={effectiveRole === "client_manager"}
                    style={{ width: "100%", padding: "0.6rem", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
                  >
                    <option value="">Selecione...</option>
                    {clients.map((client) => (
                      <option key={client.id} value={client.id}>{client.name}</option>
                    ))}
                  </select>
                </div>
              )}
              {error && (
                <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>
                  {error}
                </div>
              )}
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? "Salvando..." : "Criar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {showResetModal && selectedUser && (
        <div className="modal-overlay" onClick={() => setShowResetModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Resetar senha</h3>
            <p style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>
              Defina uma nova senha para <strong>{selectedUser.email}</strong>.
            </p>
            <form onSubmit={handleResetPassword}>
              <div className="form-group">
                <label>Nova senha temporária *</label>
                <input
                  required
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                />
              </div>
              {resetError && <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>{resetError}</div>}
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowResetModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={resettingPassword}>
                  {resettingPassword ? "Salvando..." : "Salvar nova senha"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
