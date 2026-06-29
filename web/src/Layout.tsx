import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import { LOGO_URL } from "./assets/placeholder-logo";

export default function Layout() {
  const { user, logout } = useAuth();

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
          <NavLink to="/clientes">Clientes</NavLink>
          <NavLink to="/impressoras">Impressoras</NavLink>
          <NavLink to="/alertas">Alertas</NavLink>
          <NavLink to="/agentes">Agentes</NavLink>
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
            {user?.username}
          </div>
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
    </div>
  );
}
