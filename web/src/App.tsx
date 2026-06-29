import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./Layout";
import Dashboard from "./pages/Dashboard";
import Clientes from "./pages/Clientes";
import Impressoras from "./pages/Impressoras";
import Alertas from "./pages/Alertas";
import Agentes from "./pages/Agentes";
import { Login } from "./pages/Login";

function ProtectedRoutes() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        background: "#0f172a",
        color: "#fff",
        fontSize: "1.25rem",
      }}>
        Carregando...
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  return (
    <Layout>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="clientes" element={<Clientes />} />
        <Route path="impressoras" element={<Impressoras />} />
        <Route path="alertas" element={<Alertas />} />
        <Route path="agentes" element={<Agentes />} />
      </Routes>
    </Layout>
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<ProtectedRoutes />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
