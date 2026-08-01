import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";
import type { Partner, PartnerBillingStats } from "../types";

export default function Revendedores() {
  const { user } = useAuth();
  const isSuperadmin = (user?.role || "superadmin") === "superadmin";
  const [partners, setPartners] = useState<Partner[]>([]);
  const [partnerStats, setPartnerStats] = useState<PartnerBillingStats[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    logo_url: "",
    active: true,
  });

  const load = async () => {
    const [partnersData, statsData] = await Promise.all([
      api.getPartners(),
      api.getPartnerStats(),
    ]);
    setPartners(partnersData);
    setPartnerStats(statsData);
  };

  useEffect(() => {
    if (!isSuperadmin) return;
    load();
  }, [isSuperadmin]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.createPartner({
        name: form.name.trim(),
        logo_url: form.logo_url.trim() || null,
        active: form.active,
      });
      setShowModal(false);
      setForm({ name: "", logo_url: "", active: true });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao criar revendedor");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (partner: Partner) => {
    await api.updatePartner(partner.id, { active: !partner.active });
    await load();
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

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Revendedores</h1>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Novo revendedor</button>
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
                <th>Revendedor</th>
                <th>Clientes</th>
                <th>Impressoras</th>
                <th>Cobradas</th>
                <th>Online</th>
                <th>Offline</th>
                <th>Logo</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {partners.map((partner) => {
                const stats = partnerStats.find((item) => item.partner_id === partner.id);
                return (
                <tr key={partner.id}>
                  <td>{partner.name}</td>
                  <td>{stats?.total_clients ?? 0}</td>
                  <td>{stats?.total_printers ?? 0}</td>
                  <td>
                    <strong>{stats?.billable_printers ?? 0}</strong>
                  </td>
                  <td>{stats?.online_printers ?? 0}</td>
                  <td>{stats?.offline_printers ?? 0}</td>
                  <td>
                    {partner.logo_url ? (
                      <a href={partner.logo_url} target="_blank" rel="noreferrer">
                        Ver logo
                      </a>
                    ) : (
                      "Sem logo"
                    )}
                  </td>
                  <td>
                    <span className={`badge ${partner.active ? "online" : "offline"}`}>
                      {partner.active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-ghost" onClick={() => toggleActive(partner)}>
                      {partner.active ? "Desativar" : "Ativar"}
                    </button>
                  </td>
                </tr>
              )})}
            </tbody>
          </table>
        )}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Novo revendedor</h3>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Nome *</label>
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>URL da logo</label>
                <input
                  placeholder="https://site.com/logo.png"
                  value={form.logo_url}
                  onChange={(e) => setForm({ ...form, logo_url: e.target.value })}
                />
                <small style={{ color: "var(--text-muted)" }}>
                  Se preencher, o ZIP do instalador tenta incluir essa logo na entrega comercial. Para aparecer dentro da janela do instalador, a forma mais garantida continua sendo usar um arquivo BMP chamado logo-revendedor.bmp ao lado do PrintCollectSetup.exe.
                </small>
              </div>
              {form.logo_url && (
                <div style={{ marginBottom: "1rem" }}>
                  <img
                    src={form.logo_url}
                    alt="Prévia da logo"
                    style={{ maxWidth: "220px", maxHeight: "80px", objectFit: "contain", background: "#fff", padding: "0.5rem", borderRadius: "8px" }}
                  />
                </div>
              )}
              {error && <div style={{ color: "var(--danger)", marginBottom: "1rem" }}>{error}</div>}
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
    </>
  );
}
