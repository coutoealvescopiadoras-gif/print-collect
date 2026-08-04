import { NavLink, Outlet } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "./context/AuthContext";
import { api } from "./api";
import { LOGO_URL } from "./assets/placeholder-logo";

export default function Layout() {
  const { user, logout } = useAuth();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");
  const effectiveRole = user ? (user.role || "superadmin") : null;
  const isSuperadmin = effectiveRole === "superadmin";
  const isPartnerAdmin = effectiveRole === "partner_admin";
  const canManageResources = effectiveRole === "superadmin" || effectiveRole === "partner_admin" || effectiveRole === "client_manager";
  const canManageUsers = canManageResources;
  const canManageInstaller = isSuperadmin || isPartnerAdmin;
  const roleLabel =
    effectiveRole === "superadmin"
      ? "Superadmin"
      : effectiveRole === "partner_admin"
        ? "Revendedor"
      : effectiveRole === "client_manager"
        ? "Gestor do cliente"
        : "Cliente";

  return (
    <div className="layout">
      <aside className="sidebar">
        <div style={{ 
          display: "flex", 
          alignItems: "center", 
          gap: "0.75rem", 
          marginBottom: "2rem" 
        }}>
          <img 
            src={LOGO_URL} 
            alt="C&A Soluções"
            style={{
              width: "160px",
              height: "auto",
              borderRadius: "0",
              objectFit: "contain",
              backgroundColor: "transparent",
              mixBlendMode: "multiply",
              filter: "brightness(1.2) saturate(1.3)",
            }}
          />
        </div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          {isSuperadmin && <NavLink to="/revendedores">Revendedores</NavLink>}
          {canManageResources && <NavLink to="/clientes">Clientes</NavLink>}
          {canManageInstaller && <NavLink to="/instalador">📦 Instalador</NavLink>}
          <NavLink to="/impressoras">Impressoras</NavLink>
          <NavLink to="/alertas">Alertas</NavLink>
          {canManageResources && <NavLink to="/agentes">Agentes</NavLink>}
          {canManageUsers && <NavLink to="/usuarios">Usuários</NavLink>}
        </nav>
        <div style={{
          marginTop: "auto",
          padding: "1rem",
          borderTop: "1px solid #334155",
        }}>
          <div style={{
            color: "#94a3b8",
            fontSize: "0.875rem",
            marginBottom: "0.5rem",
          }}>
            {user?.email || user?.username}
          </div>
          <div style={{
            color: "#64748b",
            fontSize: "0.75rem",
            marginBottom: "0.75rem",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}>
            {roleLabel || ""}
          </div>
          <button
            onClick={() => {
              setPasswordError("");
              setPasswordSuccess("");
              setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
              setShowPasswordModal(true);
            }}
            style={{
              width: "100%",
              padding: "0.5rem",
              borderRadius: "6px",
              border: "none",
              background: "transparent",
              color: "#94a3b8",
              cursor: "pointer",
              fontSize: "0.875rem",
              textAlign: "left",
              transition: "all 0.2s",
              marginBottom: "0.25rem",
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = "#1e293b";
              e.currentTarget.style.color = "#fff";
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "#94a3b8";
            }}
          >
            Trocar senha
          </button>
          <button
            onClick={logout}
            style={{
              width: "100%",
              padding: "0.5rem",
              borderRadius: "6px",
              border: "none",
              background: "transparent",
              color: "#94a3b8",
              cursor: "pointer",
              fontSize: "0.875rem",
              textAlign: "left",
              transition: "all 0.2s",
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = "#1e293b";
              e.currentTarget.style.color = "#fff";
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "#94a3b8";
            }}
          >
            Sair
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
      {showPasswordModal && (
        <div className="modal-overlay" onClick={() => setShowPasswordModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Trocar senha</h3>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setPasswordError("");
                setPasswordSuccess("");
                if (passwordForm.newPassword.length < 6) {
                  setPasswordError("A nova senha deve ter pelo menos 6 caracteres.");
                  return;
                }
                if (passwordForm.newPassword !== passwordForm.confirmPassword) {
                  setPasswordError("A confirmação da senha não confere.");
                  return;
                }
                try {
                  setPasswordSaving(true);
                  await api.changeOwnPassword(passwordForm.currentPassword, passwordForm.newPassword);
                  setPasswordSuccess("Senha alterada com sucesso.");
                  setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
                } catch (err) {
                  setPasswordError(err instanceof Error ? err.message : "Erro ao alterar senha");
                } finally {
                  setPasswordSaving(false);
                }
              }}
            >
              <div className="form-group">
                <label>Senha atual *</label>
                <input
                  required
                  type="password"
                  value={passwordForm.currentPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, currentPassword: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Nova senha *</label>
                <input
                  required
                  type="password"
                  value={passwordForm.newPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Confirmar nova senha *</label>
                <input
                  required
                  type="password"
                  value={passwordForm.confirmPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                />
              </div>
              {passwordError && <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>{passwordError}</div>}
              {passwordSuccess && <div style={{ color: "var(--success)", marginBottom: "1rem" }}>{passwordSuccess}</div>}
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowPasswordModal(false)}>Fechar</button>
                <button type="submit" className="btn btn-primary" disabled={passwordSaving}>
                  {passwordSaving ? "Salvando..." : "Salvar nova senha"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
