import { useEffect, useState } from "react";
import { api } from "../api";
import type { Partner, Printer } from "../types";
import { formatDateTimeBrasil, formatNumberBrasil } from "../utils";
import { useAuth } from "../context/AuthContext";

function TonerBar({ level }: { level: number | null }) {
  if (level === null) return <span>—</span>;
  const cls = level <= 5 ? "critical" : level <= 15 ? "low" : "ok";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <div className="toner-bar">
        <div className={`toner-bar-fill ${cls}`} style={{ width: `${level}%` }} />
      </div>
      <span style={{ fontSize: "0.8rem" }}>{level}%</span>
    </div>
  );
}

export default function Impressoras() {
  const { user, loading: authLoading } = useAuth();
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(false);

  const effectiveRole = user ? (user.role || "superadmin") : null;
  const isSuperadmin = effectiveRole === "superadmin";
  const isPartnerAdmin = effectiveRole === "partner_admin";
  const hasAnyPartnerVisible = printers.some((p) => p.partner_name && p.partner_id);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);

  const canManagePrinters =
    !authLoading &&
    !!user &&
    (isSuperadmin || isPartnerAdmin || effectiveRole === "client_manager");

  const [ownOnly, setOwnOnly] = useState<boolean>(true);
  const [partnerId, setPartnerId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState<string>("");
  const [searchDebounced, setSearchDebounced] = useState<string>("");

  // Debounce do texto de pesquisa (1 espera 400ms apos digitar para atualizar listagem
  useEffect(() => {
    const id = setTimeout(() => {
      setSearchDebounced(searchText);
    }, 400);
    return () => clearTimeout(id);
  }, [searchText]);

  // Carrega parceiros se for superadmin
  useEffect(() => {
    if (!isSuperadmin) return;
    api.getPartners().then(setPartners).catch(() => setPartners([]));
  }, [isSuperadmin]);

  const load = async (showLoading = false) => {
    if (authLoading || !user) return;
    if (showLoading) setLoading(true);
    try {
      const params: Parameters<typeof api.getPrinters>[0] = {};
      if (isSuperadmin) {
        params.own_only = ownOnly;
        if (!ownOnly && partnerId !== null) params.partner_id = partnerId;
      }
      if (searchDebounced.trim()) params.search = searchDebounced.trim();
      const data = await api.getPrinters(params);
      setPrinters(data);
      setLastRefreshAt(new Date());
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, ownOnly, partnerId, searchDebounced]);

  useEffect(() => {
    if (authLoading || !user) return;
    const id = window.setInterval(() => {
      load(false);
    }, 60000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  const handleRemovePrinter = async (printer: Printer) => {
    const model = printer.model || printer.ip_address || "esta impressora";
    const ok = window.confirm(
      `Confirma REMOVER "${model}"?\n\n` +
        `Ela NÃO será mais monitorada e NÃO voltará a aparecer automaticamente, mesmo que seja encontrada na rede na próxima coleta.\n\n` +
        `(Se mudar de ideia depois, crie uma impressora manualmente com o mesmo IP/serial, ou contate o suporte.)`,
    );
    if (!ok) return;

    try {
      await api.ignorePrinter(printer.id);
      setPrinters((current) => current.filter((p) => p.id !== printer.id));
    } catch (e: any) {
      window.alert("Erro ao remover impressora: " + String(e?.message || e));
    }
  };

  const limparFiltros = () => {
    setOwnOnly(true);
    setPartnerId(null);
    setSearchText("");
    setSearchDebounced("");
  };

  const temFiltroAplicado =
    !ownOnly || partnerId !== null || searchDebounced.trim().length > 0;

  return (
    <>
      <div
        style={{
          display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        flexWrap: "wrap",
        gap: "1rem",
        marginBottom: "1rem",
      }}
      >
        <h1 className="page-title" style={{ marginBottom: 0 }}>
          Impressoras
        </h1>
        {lastRefreshAt && (
          <div
            style={{
              fontSize: "0.8rem",
              color: "var(--text-muted)",
              padding: "0.35rem 0.7rem",
              borderRadius: 999,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
            }}
          >
            <span style={{ color: "var(--success)" }}>●</span>
            Atualizado em {formatDateTimeBrasil(lastRefreshAt)}
          </div>
        )}
      </div>

      <div
        className="card"
        style={{
          marginBottom: "1rem",
          padding: "0.75rem 1rem",
          background: "var(--surface-2)",
        }}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: "1.25rem",
          }}
        >
          {isSuperadmin && (
            <div>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  fontSize: "0.85rem",
                  marginBottom: 4,
                  color: "var(--text-muted)",
                }}
              >
                Mostrar
              </label>
              <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                <label
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="radio"
                    name="scope_own"
                    checked={ownOnly}
                    onChange={() => {
                      setOwnOnly(true);
                      setPartnerId(null);
                    }}
                  />
                  <span>
                    <strong>Apenas meus clientes</strong> (diretos, sem parceiro)
                  </span>
                </label>
                <label
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="radio"
                    name="scope_own"
                    checked={!ownOnly}
                    onChange={() => {
                      setOwnOnly(false);
                    }}
                  />
                  <span>Todos os clientes</span>
                </label>
              </div>
            </div>
          )}

          {isSuperadmin && !ownOnly && partners.length > 0 && (
            <div>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  fontSize: "0.85rem",
                  marginBottom: 4,
                  color: "var(--text-muted)",
                }}
              >
                🤝 Parceiro
              </label>
              <select
                className="input"
                value={partnerId === null ? "" : String(partnerId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setPartnerId(v === "" ? null : Number(v));
                }}
                style={{ minWidth: 180 }}
              >
                <option value="">Todos os parceiros</option>
                {partners.map((pt) => (
                  <option key={pt.id} value={pt.id}>
                  {pt.name}
                </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ flex: "1 1 200px", minWidth: 200, maxWidth: 480 }}>
            <label
              style={{
                display: "block",
                fontWeight: 600,
                fontSize: "0.85rem",
                marginBottom: 4,
                color: "var(--text-muted)",
              }}
            >
              🔍 Pesquisar cliente
            </label>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input
                className="input"
                type="search"
                placeholder="Digite o nome do cliente..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                style={{ flex: 1 }}
              />
              {temFiltroAplicado && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={limparFiltros}
                  title="Limpar filtros"
                >
                  Limpar
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <div className="empty">Carregando impressoras...</div>
        ) : printers.length === 0 ? (
          <div className="empty">
            {temFiltroAplicado
              ? "Nenhuma impressora encontrada com estes filtros. Tente limpar os filtros."
              : "Nenhuma impressora registrada. Instale um agente no cliente para coleta automática."}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Cliente</th>
                {(isSuperadmin || hasAnyPartnerVisible) && <th>Parceiro</th>}
                <th>Modelo</th>
                <th>IP</th>
                <th>Serial</th>
                <th>Status</th>
                <th>Páginas</th>
                <th>Toner</th>
                <th>Última coleta</th>
                {canManagePrinters && <th style={{ width: 110 }}>Ações</th>}
              </tr>
            </thead>
            <tbody>
              {printers.map((p) => (
                <tr key={p.id}>
                  <td>
                  <strong>{p.client_name || "—"}</strong>
                </td>
                {(isSuperadmin || hasAnyPartnerVisible) && (
                  <td style={{ color: "var(--text-muted)" }}>
                    {p.partner_name || <span style={{ opacity: 0.6 }}>—</span>}
                  </td>
                )}
                  <td>
                    <div>{p.model || "—"}</div>
                    {p.manufacturer && (
                      <small style={{ color: "var(--text-muted)" }}>
                        {p.manufacturer}
                      </small>
                    )}
                  </td>
                  <td>{p.ip_address}</td>
                  <td>{p.serial_number || "—"}</td>
                  <td>
                    <span className={`badge ${p.status}`}>{p.status}</span>
                  </td>
                  <td>{formatNumberBrasil(p.pages_total)}</td>
                  <td>
                    <TonerBar level={p.toner_black} />
                  </td>
                  <td>{formatDateTimeBrasil(p.last_seen)}</td>
                  {canManagePrinters && (
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{
                          color: "var(--danger)",
                          borderColor: "transparent",
                          background: "transparent",
                          padding: "0.3rem 0.6rem",
                          fontSize: 13,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                        title="Remover esta impressora do monitoramento"
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "rgba(239, 68, 68, 0.08)";
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "rgba(239, 68, 68, 0.3)";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "transparent";
                          (e.currentTarget as HTMLButtonElement).style.background =
                            "transparent";
                        }}
                        onClick={() => handleRemovePrinter(p)}
                      >
                        🗑️ Remover
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
