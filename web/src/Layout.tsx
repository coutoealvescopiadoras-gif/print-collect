import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { api } from "./api";

export default function Layout() {
  const { user, branding, logout, loading } = useAuth();
  const navigate = useNavigate();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current: "",
    new: "",
    confirm: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // ⛔ GUARD INQUEBRÁVEL V2: NÃO RENDERIZA NADA (NENHUM ELEMENTO, NENHUMA IMAGEM!)
  //     ATÉ TER user + branding (null = ainda não carregou -> NÃO PINTA NADA!)
  //     Isso ELIMINA 100% qualquer frame com logo de C&A antes da logo do revendedor.
  if (loading || !user || !branding) {
    return (
      <>
        <style>{`
          @keyframes pc-spin-v2 { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        `}</style>
        <div
          style={{
            position: "fixed",
            inset: 0,
            width: "100vw",
            height: "100vh",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            // COR EXATA DO MODO ESCURO (sem usar variaveis CSS que poderiam demorar a carregar!)
            background: "#0b1220",
            backgroundColor: "#0b1220",
            zIndex: 999999,
            gap: "1rem",
            margin: 0,
            padding: 0,
          }}
        >
          <div
            style={{
              width: 64,
              height: 64,
              border: "6px solid #1e293b",
              borderTopColor: "#2563eb",
              borderRadius: "50%",
              animation: "pc-spin-v2 900ms linear infinite",
            }}
          />
          <div style={{ color: "#94a3b8", fontSize: 14, fontWeight: 500, letterSpacing: 0.3 }}>
            Carregando dados do painel...
          </div>
        </div>
      </>
    );
  }

  const effectiveRole = user ? (user.role || "superadmin") : null;
  const isSuperadmin = effectiveRole === "superadmin";
  const isPartnerAdmin = effectiveRole === "partner_admin";
  const isPartnerStaff = effectiveRole === "partner_staff";
  const isClientManager = effectiveRole === "client_manager";
  const isPartner = isPartnerAdmin || isPartnerStaff; // unifica revendedor + colaborador da revenda
  const canViewClients = !!user; // TODOS usuarios logados VEEM aba Clientes (viewer ve o seu; staff/admin veem do parceiro)
  const canViewAgents = isSuperadmin || isPartner || isClientManager; // Cliente Final NAO VE Agentes
  const canManageUsers = isSuperadmin || isPartnerAdmin; // Colaborador NAO gerencia outros usuarios (mais seguro!)
  const canManageInstaller = isSuperadmin || isPartnerAdmin;
  const roleLabel =
    effectiveRole === "superadmin"
      ? "Superadmin"
      : effectiveRole === "partner_admin"
        ? "Revendedor"
        : effectiveRole === "partner_staff"
          ? "Colaborador"
          : effectiveRole === "client_manager"
            ? "Gestor"
            : effectiveRole === "client_viewer"
              ? "Cliente Final"
              : "";

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    if (passwordForm.new !== passwordForm.confirm) {
      setError("Nova senha e confirmação não batem");
      setSaving(false);
      return;
    }
    if (passwordForm.new.length < 6) {
      setError("Nova senha deve ter pelo menos 6 caracteres");
      setSaving(false);
      return;
    }
    try {
      await api.changeOwnPassword(passwordForm.current, passwordForm.new);
      window.alert("Senha alterada com sucesso!");
      setShowPasswordModal(false);
      setPasswordForm({ current: "", new: "", confirm: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao trocar senha. Verifique a senha atual.");
    } finally {
      setSaving(false);
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div style={{ padding: "1.5rem 1rem", borderBottom: "1px solid var(--border)", marginBottom: "1rem" }}>
          {isSuperadmin ? (
            <div>
              <img
                src={branding.logo_src}
                alt={branding.display_name}
                style={{
                  width: "160px",
                  height: "auto",
                  borderRadius: "0",
                  objectFit: "contain",
                }}
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
          ) : (
            <div style={{ textAlign: "center" }}>
              <img
                src={branding.logo_src}
                alt={branding.display_name}
                style={{
                  width: "160px",
                  height: "auto",
                  objectFit: "contain",
                  maxWidth: "100%",
                  marginBottom: "0.5rem",
                  background: "#fff",
                  padding: 8,
                  borderRadius: 8,
                }}
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
              <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 2 }}>{branding.display_name}</div>
              {branding.tagline && branding.tagline !== branding.display_name && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                  {branding.tagline}
                </div>
              )}
              {roleLabel && (
                <div style={{ marginTop: 6, fontSize: 12 }}>
                  <span className={`badge offline`}>{roleLabel}</span>
                </div>
              )}
            </div>
          )}
        </div>

        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          {isSuperadmin && <NavLink to="/revendedores">Revendedores</NavLink>}
          {canViewClients && <NavLink to="/clientes">Clientes</NavLink>}
          {canManageInstaller && <NavLink to="/instalador">Instalador</NavLink>}
          <NavLink to="/alertas">Alertas</NavLink>
          {canViewAgents && <NavLink to="/agentes">Agentes</NavLink>}
          {canManageUsers && <NavLink to="/usuarios">Usuários</NavLink>}
        </nav>

        <div style={{
          marginTop: "auto",
          padding: "1rem",
          borderTop: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}>
          <div style={{ fontSize: 14, wordBreak: "break-all" }}>
            <strong>{user?.email}</strong>
          </div>
          <button
            className="btn btn-ghost"
            style={{ justifyContent: "flex-start" }}
            onClick={() => setShowPasswordModal(true)}
          >
            🔑 Trocar senha
          </button>
          <button className="btn btn-ghost" style={{ color: "var(--danger)", justifyContent: "flex-start" }} onClick={handleLogout}>
            Sair
          </button>
        </div>
      </aside>

      <main className="content">
        <Outlet />
      </main>

      {showPasswordModal && (
        <div className="modal-overlay" onClick={() => setShowPasswordModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Trocar senha</h3>
            <form onSubmit={handlePassword}>
              <div className="form-group">
                <label>Senha atual</label>
                <input
                  type="password"
                  value={passwordForm.current}
                  onChange={(e) => setPasswordForm({ ...passwordForm, current: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Nova senha (mínimo 6 caracteres)</label>
                <input
                  type="password"
                  value={passwordForm.new}
                  onChange={(e) => setPasswordForm({ ...passwordForm, new: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Confirme a nova senha</label>
                <input
                  type="password"
                  value={passwordForm.confirm}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirm: e.target.value })}
                  required
                />
              </div>
              {error && <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>{error}</div>}
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowPasswordModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? "Salvando..." : "Salvar nova senha"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
