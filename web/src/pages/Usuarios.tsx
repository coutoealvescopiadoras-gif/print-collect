import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";
import type { Client, Partner, User } from "../types";

type RoleValue = User["role"];

interface RoleOption {
  value: RoleValue;
  label: string;
  badgeClass: string;
}

const ROLE_DEFS: Record<RoleValue, RoleOption> = {
  superadmin: {
    value: "superadmin",
    label: "👑 Superadmin",
    badgeClass: "badge"
  },
  partner_admin: {
    value: "partner_admin",
    label: "🏢 Revendedor (Admin)",
    badgeClass: "badge online"
  },
  partner_staff: {
    value: "partner_staff",
    label: "👷 Colaborador (equipe revenda)",
    badgeClass: "badge"
  },
  client_manager: {
    value: "client_manager",
    label: "⚙️ Gestor do Cliente (edita tudo)",
    badgeClass: "badge offline"
  },
  client_viewer: {
    value: "client_viewer",
    label: "🧑‍💼 Cliente Final (acompanha só suas máquinas)",
    badgeClass: "badge"
  },
} as const;

function RoleBadge({ role }: { role: RoleValue }) {
  const def = ROLE_DEFS[role] || { label: role, badgeClass: "badge" };
  const customStyle: React.CSSProperties | null = (() => {
    switch (role) {
      case "superadmin":
        return {
          background: "rgba(124, 58, 237, 0.12)",
          color: "#7c3aed",
          border: "1px solid rgba(124, 58, 237, 0.3)",
          fontWeight: 700,
        };
      case "partner_admin":
        return null;
      case "partner_staff":
        return {
          background: "rgba(37, 99, 235, 0.12)",
          color: "#2563eb",
          border: "1px solid rgba(37, 99, 235, 0.3)",
          fontWeight: 600,
        };
      case "client_manager":
        return null;
      case "client_viewer":
        return {
          background: "rgba(71, 85, 105, 0.08)",
          color: "#334155",
          border: "1px solid rgba(71, 85, 105, 0.2)",
          fontWeight: 500,
        };
      default:
        return null;
    }
  })();
  const shortLabel: Record<RoleValue, string> = {
    superadmin: "👑 Admin Geral",
    partner_admin: "🏢 Revendedor",
    partner_staff: "👷 Colaborador",
    client_manager: "⚙️ Gestor",
    client_viewer: "🧑‍💼 Cliente Final",
  };
  return (
    <span className={def.badgeClass} style={customStyle || undefined} title={def.label}>
      {shortLabel[role] || role}
    </span>
  );
}

export default function Usuarios() {
  const { user: currentUser, loading: authLoading } = useAuth();
  const effectiveRole: RoleValue = (currentUser?.role as RoleValue) || "superadmin";
  const isSuperadmin = effectiveRole === "superadmin";
  const isPartnerAdmin = effectiveRole === "partner_admin";
  const isPartnerStaff = effectiveRole === "partner_staff";
  const canManageUsers = isSuperadmin || isPartnerAdmin; // partner_staff e client_manager NAO CRIAM usuarios (mais seguro)

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
    role: "client_viewer" as RoleValue,
    client_id: (currentUser?.client_id as number) || 0,
    partner_id: (currentUser?.partner_id as number) || 0,
  });

  const load = async () => {
    const usersPromise = api.getUsers();
    const clientsPromise = (() => {
      if (isPartnerAdmin || isPartnerStaff) {
        // Revendedor: filtrar clientes SEU (já o backend já filtra mas por seguranca filtra no front também)
        return api.getClients().then((list) =>
          list.filter((c) => !currentUser?.partner_id || c.partner_id === currentUser.partner_id || !c.partner_id)
        );
      }
      return api.getClients();
    })();
    const partnersPromise = isSuperadmin ? api.getPartners() : Promise.resolve<Partner[]>([]);
    const [usersData, clientsData, partnersData] = await Promise.all([
      usersPromise,
      clientsPromise,
      partnersPromise,
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
      const isStaff = form.role === "partner_staff";
      const isPartnerRole = form.role === "partner_admin" || isStaff;
      const payloadClientId =
        form.role === "superadmin" || isPartnerRole ? null : (form.client_id || currentUser?.client_id || null) as number | null;
      const payloadPartnerId =
        form.role === "partner_admin"
          ? (isSuperadmin ? (form.partner_id || null) : (currentUser?.partner_id || null))
          : isStaff
          ? (currentUser?.partner_id || null)
          : isSuperadmin && form.role !== "superadmin"
          ? null
          : null;
      await api.createUser({
        email: form.email,
        password: form.password,
        role: form.role,
        client_id: payloadClientId,
        partner_id: payloadPartnerId,
      });
      setShowModal(false);
      setForm({
        email: "",
        password: "",
        role: "client_viewer",
        client_id: (currentUser?.client_id as number) || 0,
        partner_id: (currentUser?.partner_id as number) || 0,
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
    const roleLabel = ROLE_DEFS[item.role]?.label || item.role;
    const confirm1 = window.confirm(
      `⚠️ EXCLUIR USUÁRIO PERMANENTEMENTE?\n\nLogin: ${item.email}\nPerfil: ${roleLabel}\n\n📢 ESTA AÇÃO NÃO PODE SER DESFEITA!`
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

  const showPartnerDropdown = isSuperadmin && (form.role === "partner_admin" || form.role === "partner_staff");
  const showClientDropdown = form.role !== "superadmin" && form.role !== "partner_admin" && form.role !== "partner_staff";

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
                <th>Cliente vinculado</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((item) => (
                <tr key={item.id}>
                  <td>{item.email}</td>
                  <td>{item.email}</td>
                  <td><RoleBadge role={item.role} /></td>
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
            {!isSuperadmin && (
              <div
                style={{
                  padding: "0.8rem 1rem",
                  marginBottom: "1rem",
                  borderRadius: "var(--radius)",
                  background: "rgba(37, 99, 235, 0.08)",
                  border: "1px solid rgba(37, 99, 235, 0.25)",
                  color: "#1d4ed8",
                  fontSize: "0.9rem",
                }}
              >
                ℹ️ Como revendedor, você pode criar:
                <br /><strong>👷 Colaborador</strong> (sua equipe, vê tudo do seu revendedor)
                <br /><strong>⚙️ Gestor do Cliente</strong> (edita um cliente específico seu)
                <br /><strong>🧑‍💼 Cliente Final</strong> (só visualiza as máquinas do cliente vinculado)
              </div>
            )}
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>E-mail / Login *</label>
                <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Senha * (mínimo 6 caracteres)</label>
                <input required type="password" minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Perfil *</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value as RoleValue })}
                  style={{ width: "100%", padding: "0.6rem", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
                >
                  {Object.values(ROLE_DEFS)
                    .filter((role) => {
                      if (isSuperadmin) return true;
                      // ===== REGRAS JULIO NO FRONTEND: =====
                      // Partner_admin (revendedor): NUNCA vê opcao "Superadmin" e NUNCA vê "Revendedor (Admin)"!
                      // Partner_admin PODE criar: Colaborador, Gestor, Cliente Final
                      if (isPartnerAdmin) {
                        return role.value === "partner_staff" || role.value === "client_manager" || role.value === "client_viewer";
                      }
                      // Qualquer outro perfil: NENHUM (canManageUsers já bloqueia acima, mas safe)
                      return false;
                    })
                    .map((role) => (
                      <option key={role.value} value={role.value}>{role.label}</option>
                    ))}
                </select>
              </div>
              {showPartnerDropdown && (
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
              {showClientDropdown && (
                <div className="form-group">
                  <label>Cliente * (vincular a este cliente)</label>
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
              {form.role === "partner_staff" && (
                <div style={{ padding: "0.6rem 0.9rem", marginBottom: "1rem", borderRadius: "var(--radius)", background: "rgba(37, 99, 235, 0.06)", border: "1px solid rgba(37, 99, 235, 0.2)", color: "#1e40af", fontSize: "0.88rem" }}>
                  ✅ Este colaborador será automaticamente vinculado ao seu revendedor e terá acesso a todos os clientes do seu revendedor, mas NÃO poderá criar outros revendedores.
                </div>
              )}
              {form.role === "client_viewer" && (
                <div style={{ padding: "0.6rem 0.9rem", marginBottom: "1rem", borderRadius: "var(--radius)", background: "rgba(71, 85, 105, 0.06)", border: "1px solid rgba(71, 85, 105, 0.2)", color: "#334155", fontSize: "0.88rem" }}>
                  🧑‍💼 O cliente final só acessa as impressoras e histórico do cliente selecionado acima. Não pode editar nada.
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
                  minLength={6}
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
