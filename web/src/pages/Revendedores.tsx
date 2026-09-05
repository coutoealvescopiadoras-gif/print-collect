import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";
import type { Partner, PartnerBillingStats } from "../types";

function getPartnerLogoSrc(partner: { logo_data: string | null; logo_url: string | null }): string | null {
  if (partner.logo_data) return partner.logo_data;
  if (partner.logo_url) return partner.logo_url;
  return null;
}

function fileToDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Erro ao ler arquivo"));
    reader.readAsDataURL(file);
  });
}

const MAX_LOGO_MB = 2;

type EditMode = "create" | "edit";

export default function Revendedores() {
  const { user, loading: authLoading } = useAuth();
  const isSuperadmin = (user?.role || "superadmin") === "superadmin";
  const [partners, setPartners] = useState<Partner[]>([]);
  const [partnerStats, setPartnerStats] = useState<PartnerBillingStats[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editMode, setEditMode] = useState<EditMode>("create");
  const [editingPartnerId, setEditingPartnerId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showUrlField, setShowUrlField] = useState(false);
  const [deletingPartnerId, setDeletingPartnerId] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "",
    logo_url: "",
    logo_data: "",
    active: true,
    admin_email: "",
    admin_password: "",
    admin_confirm_password: "",
  });

  const resetForm = () => {
    setForm({ name: "", logo_url: "", logo_data: "", active: true, admin_email: "", admin_password: "", admin_confirm_password: "" });
    setShowUrlField(false);
    setError("");
    setEditingPartnerId(null);
  };

  const load = async () => {
    const [partnersData, statsData] = await Promise.all([
      api.getPartners(),
      api.getPartnerStats(),
    ]);
    setPartners(partnersData);
    setPartnerStats(statsData);
  };

  useEffect(() => {
    if (authLoading || !user || !isSuperadmin) return;
    load();
  }, [authLoading, user, isSuperadmin]);

  const openCreate = () => {
    setEditMode("create");
    resetForm();
    setShowModal(true);
  };

  const openEdit = (partner: Partner) => {
    setEditMode("edit");
    setEditingPartnerId(partner.id);
    setForm({
      name: partner.name,
      logo_url: partner.logo_url || "",
      logo_data: partner.logo_data || "",
      active: partner.active,
      admin_email: "",
      admin_password: "",
      admin_confirm_password: "",
    });
    setShowUrlField(!!partner.logo_url && !partner.logo_data);
    setError("");
    setShowModal(true);
  };

  const generateStrongPassword = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&";
    let out = "";
    for (let i = 0; i < 12; i++) {
      out += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setForm((curr) => ({ ...curr, admin_password: out, admin_confirm_password: out }));
    // Exibe alerta para o usuario copiar
    setTimeout(() => {
      window.alert("Senha temporária gerada:\n\n" + out + "\n\nCopie essa senha e envie para o responsável pelo revendedor.\n(Ela também já está preenchida no formulário.)");
    }, 50);
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_LOGO_MB * 1024 * 1024) {
      window.alert(
        `Arquivo muito grande! Escolha uma imagem com no máximo ${MAX_LOGO_MB}MB.\n` +
          `Tamanho selecionado: ${(file.size / (1024 * 1024)).toFixed(2)}MB.`,
      );
      e.target.value = "";
      return;
    }

    if (!file.type.startsWith("image/")) {
      window.alert("Escolha um arquivo de imagem (PNG, JPG, WebP, SVG, GIF).");
      e.target.value = "";
      return;
    }

    try {
      const dataUri = await fileToDataUri(file);
      setForm((curr) => ({ ...curr, logo_data: dataUri }));
    } catch (err) {
      window.alert("Erro ao converter imagem. Tente novamente.");
    } finally {
      e.target.value = "";
    }
  };

  const handleRemoveLogo = () => {
    setForm((curr) => ({ ...curr, logo_data: "", logo_url: "" }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const adminEmail = form.admin_email.trim();
      const adminPassword = form.admin_password;
      const adminConfirm = form.admin_confirm_password;

      if (editMode === "create") {
        if (!adminEmail) {
          throw new Error("Informe o e-mail do administrador do revendedor.");
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(adminEmail)) {
          throw new Error("Formato de e-mail do administrador inválido.");
        }
        if (!adminPassword) {
          throw new Error("Informe a senha do administrador (mínimo 6 caracteres).");
        }
        if (adminPassword.length < 6) {
          throw new Error("Senha do administrador muito curta (mínimo 6 caracteres).");
        }
        if (adminPassword !== adminConfirm) {
          throw new Error("As senhas do administrador não coincidem (campos Senha e Confirmar Senha).");
        }
      }

      const payload: any = {
        name: form.name.trim(),
        logo_url: form.logo_url.trim() || null,
        logo_data: form.logo_data.trim() || null,
        active: form.active,
      };

      if (editMode === "create") {
        payload.admin_email = adminEmail;
        payload.admin_password = adminPassword;
      }

      if (editMode === "create") {
        await api.createPartner(payload);
      } else {
        if (editingPartnerId == null) throw new Error("ID do revendedor não encontrado");
        await api.updatePartner(editingPartnerId, payload);
      }

      setShowModal(false);
      resetForm();
      await load();
      if (editMode === "create") {
        window.alert(
          "✅ Revendedor criado com sucesso!\n\n" +
          "Também foi criado automaticamente o usuário administrador dele:\n" +
          "  • E-mail: " + adminEmail + "\n" +
          "  • Senha: " + adminPassword + "\n" +
          "  • Perfil: Revendedor (Admin)\n\n" +
          "Salve esses dados e envie para o responsável."
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao salvar revendedor");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (partner: Partner) => {
    await api.updatePartner(partner.id, { active: !partner.active });
    await load();
  };

  const handleDelete = async (partner: Partner) => {
    const stats = partnerStats.find((item) => item.partner_id === partner.id);
    const totalClients = stats?.total_clients ?? 0;

    let extraMsg = "";
    if (totalClients > 0) {
      extraMsg = `\n\n⚠️ IMPORTANTE: este revendedor ainda tem ${totalClients} cliente(s) vinculado(s). O sistema NÃO permitirá excluir enquanto houver clientes — primeiro remova ou reatribua esses clientes.`;
    } else {
      extraMsg = `\n\nEste revendedor não tem clientes vinculados — a exclusão será direta e irreversível.`;
    }

    const ok = window.confirm(
      `Confirma EXCLUIR o revendedor "${partner.name}"?${extraMsg}\n\nTem certeza absoluta que deseja continuar?`,
    );
    if (!ok) return;

    try {
      setDeletingPartnerId(partner.id);
      await api.deletePartner(partner.id);
      setPartners((current) => current.filter((p) => p.id !== partner.id));
      setPartnerStats((current) => current.filter((s) => s.partner_id !== partner.id));
    } catch (e: any) {
      const msg = String(e?.message || e || "Erro ao excluir revendedor");
      // Tenta extrair "detail" da resposta HTTP (FastAPI retorna {"detail":"..."})
      let detail = msg;
      try {
        if (typeof e?.response?.json === "function") {
          const obj = await e.response.json();
          if (obj?.detail) detail = String(obj.detail);
        } else if (typeof e?.data?.detail === "string") {
          detail = String(e.data.detail);
        } else if (typeof e?.detail === "string") {
          detail = String(e.detail);
        }
      } catch {
        // ignora
      }
      window.alert("Não foi possível excluir:\n\n" + detail);
    } finally {
      setDeletingPartnerId(null);
    }
  };

  if (!isSuperadmin) {
    return (
      <>
        <h1 className="page-title">Revendedores</h1>
        <div className="card">
          <div className="empty">Somente superadmin pode gerenciar revendedores.</div>
        </div>
      </>
    );
  }

  const logoPreviewSrc = form.logo_data
    ? form.logo_data
    : form.logo_url
      ? form.logo_url
      : null;

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Revendedores</h1>
        <button className="btn btn-primary" onClick={openCreate}>+ Novo revendedor</button>
      </div>

      <div className="card">
        <div style={{ marginBottom: "1rem", color: "var(--text-muted)" }}>
          Para cobrança, o sistema considera como <strong>impressoras cobradas</strong> as impressoras que tiveram leitura nos últimos 30 dias.
        </div>
        {partners.length === 0 ? (
          <div className="empty">Nenhum revendedor cadastrado</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 90 }}>Logo</th>
                <th>Revendedor</th>
                <th>Clientes</th>
                <th>Impressoras</th>
                <th>Cobradas</th>
                <th>Online</th>
                <th>Offline</th>
                <th>Status</th>
                <th style={{ width: 180 }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {partners.map((partner) => {
                const stats = partnerStats.find((item) => item.partner_id === partner.id);
                const logoSrc = getPartnerLogoSrc(partner);
                return (
                  <tr key={partner.id}>
                    <td>
                      {logoSrc ? (
                        <img
                          src={logoSrc}
                          alt={partner.name}
                          title={partner.name}
                          style={{
                            width: 64,
                            height: 40,
                            objectFit: "contain",
                            background: "#fff",
                            border: "1px solid var(--border)",
                            borderRadius: 6,
                            padding: 4,
                          }}
                          onError={(e) => {
                            (e.currentTarget as HTMLImageElement).style.display = "none";
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            width: 64,
                            height: 40,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            background: "var(--surface-hover)",
                            border: "1px dashed var(--border)",
                            borderRadius: 6,
                            color: "var(--text-muted)",
                            fontSize: 11,
                          }}
                          title="Sem logo"
                        >
                          —
                        </div>
                      )}
                    </td>
                    <td><strong>{partner.name}</strong></td>
                    <td>{stats?.total_clients ?? 0}</td>
                    <td>{stats?.total_printers ?? 0}</td>
                    <td>
                      <strong>{stats?.billable_printers ?? 0}</strong>
                    </td>
                    <td>{stats?.online_printers ?? 0}</td>
                    <td>{stats?.offline_printers ?? 0}</td>
                    <td>
                      <span className={`badge ${partner.active ? "online" : "offline"}`}>
                        {partner.active ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button className="btn btn-secondary" onClick={() => openEdit(partner)}>
                          ✏️ Editar
                        </button>
                        <button className="btn btn-ghost" onClick={() => toggleActive(partner)}>
                          {partner.active ? "Desativar" : "Ativar"}
                        </button>
                        <button
                          className="btn btn-ghost"
                          onClick={() => handleDelete(partner)}
                          disabled={deletingPartnerId === partner.id}
                          style={{ color: "var(--danger)" }}
                          title="Excluir este revendedor (só é permitido se não tiver clientes vinculados)"
                        >
                          {deletingPartnerId === partner.id ? "Excluindo..." : "🗑️ Excluir"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editMode === "create" ? "Novo revendedor" : "Editar revendedor"}</h3>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Nome *</label>
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Nome do revendedor / marca"
                />
              </div>

              <div className="form-group">
                <label>
                  Logo do revendedor{" "}
                  <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 13 }}>
                    (PNG / JPG / WebP / SVG, até {MAX_LOGO_MB}MB — recomendado fundo transparente)
                  </span>
                </label>

                <div
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                    alignItems: "center",
                    flexWrap: "wrap",
                    padding: "0.75rem",
                    background: "var(--surface-hover)",
                    borderRadius: 8,
                    border: "1px dashed var(--border)",
                  }}
                >
                  {logoPreviewSrc ? (
                    <img
                      src={logoPreviewSrc}
                      alt="Prévia da logo"
                      style={{
                        width: 140,
                        height: 64,
                        objectFit: "contain",
                        background: "#fff",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        padding: 6,
                      }}
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.opacity = "0.4";
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        width: 140,
                        height: 64,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "var(--text-muted)",
                        fontSize: 13,
                        background: "#fff",
                        border: "1px dashed var(--border)",
                        borderRadius: 8,
                      }}
                    >
                      Sem logo
                    </div>
                  )}

                  <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1, minWidth: 220 }}>
                    <label
                      className="btn btn-secondary"
                      style={{
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        justifyContent: "center",
                      }}
                    >
                      📁 Escolher arquivo do computador
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/svg+xml,image/gif"
                        style={{ display: "none" }}
                        onChange={handleFileChange}
                      />
                    </label>

                    {!showUrlField ? (
                      <button
                        type="button"
                        className="btn btn-link"
                        style={{ padding: 0, margin: 0, fontSize: 13 }}
                        onClick={() => setShowUrlField(true)}
                      >
                        🔗 Ou colar uma URL da logo (modo avançado)
                      </button>
                    ) : (
                      <div>
                        <input
                          placeholder="https://site.com/logo.png"
                          value={form.logo_url}
                          onChange={(e) => setForm({ ...form, logo_url: e.target.value })}
                          style={{ marginBottom: 4 }}
                        />
                        <button
                          type="button"
                          className="btn btn-link"
                          style={{ padding: 0, margin: 0, fontSize: 12 }}
                          onClick={() => {
                            setShowUrlField(false);
                            setForm((curr) => ({ ...curr, logo_url: "" }));
                          }}
                        >
                          ✕ Cancelar URL (usar arquivo)
                        </button>
                      </div>
                    )}

                    {logoPreviewSrc && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={handleRemoveLogo}
                        style={{ color: "var(--danger)", padding: "0.35rem 0.75rem" }}
                      >
                        🗑️ Remover logo
                      </button>
                    )}
                  </div>
                </div>

                <small style={{ color: "var(--text-muted)", marginTop: 6, display: "block" }}>
                  A logo é incluída automaticamente no ZIP do instalador para os clientes do revendedor.
                  Para aparecer DENTRO da janela do Inno Setup, continue podendo colocar um arquivo{" "}
                  <code>logo-revendedor.bmp</code> ao lado do <code>PrintCollectSetup.exe</code>.
                </small>

                <small style={{ color: "var(--text-muted)", marginTop: 10, display: "block" }}>
                  💡 Dica: se o revendedor não quiser uma logo própria, a interface dele usará automaticamente a marca <strong>Print Collect</strong> (logo genérica da plataforma).
                </small>
              </div>

              {editMode === "create" && (
                <>
                  <div
                    style={{
                      marginTop: "1.25rem",
                      padding: "1rem 1.25rem",
                      borderRadius: "var(--radius)",
                      background: "rgba(37, 99, 235, 0.06)",
                      border: "1px solid rgba(37, 99, 235, 0.25)",
                      color: "#1e3a8a",
                      fontSize: "0.92rem",
                      marginBottom: "1rem",
                    }}
                  >
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>
                      ➕ Dados de Acesso do Administrador (obrigatório)
                    </div>
                    <div style={{ color: "#1e40af", fontSize: "0.88rem" }}>
                      Preencha abaixo para criar <strong>automaticamente</strong> um usuário administrador
                      do revendedor (<em>Revendedor Admin</em>). O login será feito pelo e-mail cadastrado.
                    </div>
                    <div style={{ color: "#1e40af", fontSize: "0.88rem", marginTop: 6 }}>
                      ⛔ Esse usuário <strong>NÃO</strong> poderá cadastrar outros revendedores. Ele só
                      poderá criar colaboradores e clientes finais da sua carteira.
                    </div>
                  </div>

                  <div className="form-group">
                    <label>E-mail do administrador *</label>
                    <input
                      required
                      type="email"
                      value={form.admin_email}
                      onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                      placeholder="Ex: financeiro@ceacopiadoras.com.br"
                    />
                  </div>

                  <div className="form-group">
                    <label>
                      Senha do administrador *{" "}
                      <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 13 }}>
                        (mínimo 6 caracteres)
                      </span>
                    </label>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "stretch" }}>
                      <input
                        required
                        type="text"
                        value={form.admin_password}
                        onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                        placeholder="Digite ou gere uma senha forte"
                        style={{ flex: 1 }}
                      />
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={generateStrongPassword}
                        title="Gerar senha aleatória de 12 caracteres"
                      >
                        🔑 Gerar senha
                      </button>
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Confirmar senha *</label>
                    <input
                      required
                      type="text"
                      value={form.admin_confirm_password}
                      onChange={(e) => setForm({ ...form, admin_confirm_password: e.target.value })}
                      placeholder="Repita a mesma senha acima"
                    />
                    {form.admin_password && form.admin_confirm_password && form.admin_password !== form.admin_confirm_password && (
                      <small style={{ color: "var(--danger)", marginTop: 6, display: "block" }}>
                        ⚠️ As senhas não coincidem.
                      </small>
                    )}
                  </div>
                </>
              )}

              {editMode !== "create" && (
                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={form.active}
                      onChange={(e) => setForm({ ...form, active: e.target.checked })}
                      style={{ marginRight: 6 }}
                    />
                    Revendedor ativo
                  </label>
                </div>
              )}

              {error && <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>{error}</div>}
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setShowModal(false);
                    resetForm();
                  }}
                >
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? "Salvando..." : editMode === "create" ? "Criar" : "Salvar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
