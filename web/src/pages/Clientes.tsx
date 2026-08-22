import { Fragment, useEffect, useState } from "react";
import { api, getPublicApiUrl } from "../api";
import type { AgentPairingCode, Client, Location, Partner, Printer } from "../types";
import { useAuth } from "../context/AuthContext";
import { formatDateTimeBrasil } from "../utils";
import ModalPrinter from "../components/ModalPrinter";

function copyText(text: string) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => {
      window.prompt("Copie:", text);
    });
  } else {
    window.prompt("Copie:", text);
  }
}

export default function Clientes() {
  const { user, loading: authLoading } = useAuth();
  const effectiveRole = user?.role || "superadmin";
  const isSuperadmin = effectiveRole === "superadmin";
  const isPartnerAdmin = effectiveRole === "partner_admin";
  const canManageClients = isSuperadmin || isPartnerAdmin;
  const canEditSector = isSuperadmin || isPartnerAdmin || effectiveRole === "client_manager";

  const [partners, setPartners] = useState<Partner[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editingClientId, setEditingClientId] = useState<number | null>(null);
  const [form, setForm] = useState({ name: "", cnpj: "", contact_name: "", contact_phone: "", contact_email: "" });
  const [deletingClientId, setDeletingClientId] = useState<number | null>(null);
  const [editingSectorPrinterId, setEditingSectorPrinterId] = useState<number | null>(null);
  const [savingSectorPrinterId, setSavingSectorPrinterId] = useState<number | null>(null);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);

  // Filtros (igual aba Impressoras)
  const [ownOnly, setOwnOnly] = useState<boolean>(false);
  const [partnerId, setPartnerId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState<string>("");
  const [searchDebounced, setSearchDebounced] = useState<string>("");

  // Modal pareamento
  const [pairingClientId, setPairingClientId] = useState<number | null>(null);
  const [pairingAgentName, setPairingAgentName] = useState("");
  const [pairingTtl, setPairingTtl] = useState(1440);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const [pairingResult, setPairingResult] = useState<AgentPairingCode | null>(null);
  const [pairingCopied, setPairingCopied] = useState(false);

  // ===== MODAIS HIERÁRQUICOS (Julio pediu UI profissional) =====
  // Nível 1: Modal do Cliente (lista impressoras dele)
  const [clienteModalId, setClienteModalId] = useState<number | null>(null);
  const [impressorasClienteModal, setImpressorasClienteModal] = useState<Printer[]>([]);
  const [locaisClienteModal, setLocaisClienteModal] = useState<Location[]>([]);
  const [loadingClienteModal, setLoadingClienteModal] = useState<boolean>(false);
  // Nível 2: Modal Ficha Completa Impressora
  const [printerModalId, setPrinterModalId] = useState<number | null>(null);

  // Debounce pesquisa
  useEffect(() => {
    const id = setTimeout(() => {
      setSearchDebounced(searchText);
    }, 400);
    return () => clearTimeout(id);
  }, [searchText]);

  // Carrega parceiros (se superadmin)
  useEffect(() => {
    if (!isSuperadmin) return;
    api.getPartners().then(setPartners).catch(() => setPartners([]));
  }, [isSuperadmin]);

  const load = async () => {
    if (authLoading || !user) return;
    const params: Parameters<typeof api.getClients>[0] = {};
    if (isSuperadmin) {
      params.own_only = ownOnly;
      if (!ownOnly && partnerId !== null) params.partner_id = partnerId;
    }
    if (searchDebounced.trim()) params.search = searchDebounced.trim();
    const data = await api.getClients(params);
    setClients(data);

    setLastRefreshAt(new Date());
  };

  useEffect(() => {
    if (authLoading || !user) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, ownOnly, partnerId, searchDebounced]);

  useEffect(() => {
    if (authLoading || !user) return;
    const id = window.setInterval(() => {
      load();
    }, 60000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  const temFiltroAplicado =
    !ownOnly || partnerId !== null || searchDebounced.trim().length > 0;

  const limparFiltros = () => {
    setOwnOnly(true);
    setPartnerId(null);
    setSearchText("");
    setSearchDebounced("");
  };

  const handleOpenCreate = () => {
    setEditingClientId(null);
    setForm({ name: "", cnpj: "", contact_name: "", contact_phone: "", contact_email: "" });
    setShowModal(true);
  };

  const handleOpenEdit = (client: Client) => {
    setEditingClientId(client.id);
    setForm({
      name: client.name || "",
      cnpj: client.cnpj || "",
      contact_name: client.contact_name || "",
      contact_phone: client.contact_phone || "",
      contact_email: client.contact_email || "",
    });
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingClientId(null);
    setForm({ name: "", cnpj: "", contact_name: "", contact_phone: "", contact_email: "" });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editingClientId !== null) {
      await api.updateClient(editingClientId, form);
    } else {
      await api.createClient(form);
    }
    handleCloseModal();
    load();
  };

  const handleDelete = async (clientId: number, clientName: string) => {
    const ok = window.confirm(`Excluir o cliente "${clientName}"?\n\nIsso também apagará impressoras, leituras, alertas e agentes vinculados a ele.`);
    if (!ok) return;
    try {
      setDeletingClientId(clientId);
      await api.deleteClient(clientId);
      load();
    } finally {
      setDeletingClientId(null);
    }
  };

  // ============ MODAL CLIENTE (Nível 1 — Julio pediu! LISTA IMPRESSORAS + SETOR EDITAVEL + REMOVER) ============
  const handleAbrirModalCliente = async (clientId: number) => {
    try {
      setLoadingClienteModal(true);
      setClienteModalId(clientId);
      const [printers, locations] = await Promise.all([
        api.getPrinters({ client_id: clientId }),
        api.getLocations(clientId),
      ]);
      setImpressorasClienteModal(printers || []);
      setLocaisClienteModal(locations || []);
    } catch (e: any) {
      window.alert("Erro ao carregar impressoras e setores do cliente: " + String(e?.message || e));
    } finally {
      setLoadingClienteModal(false);
    }
  };

  const handleFecharModalCliente = () => {
    setClienteModalId(null);
    setImpressorasClienteModal([]);
    setLocaisClienteModal([]);
    setEditingSectorPrinterId(null);
    setSavingSectorPrinterId(null);
    setLoadingClienteModal(false);
  };

  const getPrinterSectorModal = (printer: Printer) => {
    if (!printer.location_id) return "—";
    const location = locaisClienteModal.find((item) => item.id === printer.location_id);
    return location ? (location.sector || location.name || "—") : "—";
  };

  const handleChangeSectorModal = async (printer: Printer, rawValue: string) => {
    if (!clienteModalId) return;
    try {
      setSavingSectorPrinterId(printer.id);
      let targetLocationId: number | null = null;
      if (rawValue === "") {
        targetLocationId = null;
      } else if (rawValue.startsWith("new:")) {
        const sectorName = rawValue.slice(4).trim();
        if (!sectorName) return;
        const created = await api.createLocation({
          client_id: clienteModalId,
          name: sectorName,
          sector: sectorName,
        });
        setLocaisClienteModal((curr) => [...curr, created]);
        targetLocationId = created.id;
      } else {
        targetLocationId = Number(rawValue) || null;
      }
      const updatedPrinter = await api.updatePrinter(printer.id, {
        location_id: targetLocationId,
      });
      setImpressorasClienteModal((curr) =>
        curr.map((p) => (p.id === printer.id ? { ...p, ...updatedPrinter } : p)),
      );
    } catch (e: any) {
      window.alert("Erro ao salvar setor: " + String(e?.message || e));
    } finally {
      setEditingSectorPrinterId(null);
      setSavingSectorPrinterId(null);
    }
  };

  const handleRemovePrinterModal = async (printer: Printer) => {
    const model = printer.model || printer.ip_address || "esta impressora";
    const ok = window.confirm(
      `Confirma REMOVER "${model}"?\n\n` +
        `Ela NÃO será mais monitorada e NÃO voltará a aparecer automaticamente, mesmo que seja encontrada na rede na próxima coleta.`,
    );
    if (!ok) return;
    try {
      await api.ignorePrinter(printer.id);
      setImpressorasClienteModal((curr) => curr.filter((p) => p.id !== printer.id));
    } catch (e: any) {
      window.alert("Erro ao remover impressora: " + String(e?.message || e));
    }
  };

  const openPairing = (client: Client) => {
    setPairingClientId(client.id);
    setPairingAgentName(`Agente ${client.name}`);
    setPairingTtl(1440);
    setPairingResult(null);
    setPairingError(null);
    setPairingCopied(false);
  };
  const closePairing = () => {
    setPairingClientId(null);
    setPairingResult(null);
    setPairingError(null);
  };

  const doGeneratePairing = async () => {
    if (!pairingClientId) return;
    try {
      setPairingLoading(true);
      setPairingError(null);
      const res = await api.generateAgentPairingCode({
        client_id: pairingClientId,
        name: pairingAgentName.trim() || undefined,
        ttl_minutes: Number(pairingTtl) || 1440,
      });
      setPairingResult(res);
    } catch (e: any) {
      setPairingError(String(e?.message || e || "Erro desconhecido"));
    } finally {
      setPairingLoading(false);
    }
  };

  const doCopyPairingCode = () => {
    if (!pairingResult) return;
    copyText(pairingResult.pairing_code);
    setPairingCopied(true);
    setTimeout(() => setPairingCopied(false), 2000);
  };

  const INSTALLER_DOWNLOAD_URL = "https://www.printcollect.com.br/PrintCollectSetup.exe";

  const buildPairingMessage = (client?: Client) => {
    const theClient = client || activePairingClient;
    const clientCode = theClient?.client_code || "<CODIGO-DO-CLIENTE>";
    return [
      "Olá, tudo bem?",
      "",
      "Estamos configurando o monitoramento automático das suas impressoras! 🖨️",
      "",
      "Siga esses 3 passos no computador principal da empresa (ou na filial):",
      "",
      `1️⃣ BAIXE o instalador no link oficial abaixo e dê DUPLA CLIQUE para instalar:`,
      `   🔗 ${INSTALLER_DOWNLOAD_URL}`,
      "2️⃣ Ao terminar a instalação, abrirá automaticamente um \"Wizard de Instalação\".",
      "3️⃣ Quando perguntar, informe SEU CÓDIGO DO CLIENTE (não expira, sempre o mesmo):",
      `     • Código do Cliente: 🎫 ${clientCode}`,
      "     • Comunidade SNMP: public (só aperte Enter)",
      "",
      "💡 Dica: Instalou na matriz, e agora quer instalar também em outras 2 filiais da mesma empresa?",
      "       Basta rodar o instalador em cada filial e usar o MESMO CÓDIGO DO CLIENTE acima!",
      "       Todas as impressoras de todas as filiais ficarão cadastradas automaticamente na sua empresa.",
      "",
      "Pronto! 😊 Em menos de 2 minutos o sistema encontra sozinho todas as impressoras da sua rede e começa a monitorar nível de toner, contadores e alertas.",
      "Qualquer dúvida é só chamar a gente!",
    ].join("\n");
  };

  const pairingInlineServerUrl = () =>
    pairingResult?.server_url || getPublicApiUrl() || "https://api.printcollect.com.br";

  const activePairingClient = pairingClientId ? clients.find((c) => c.id === pairingClientId) : null;

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <h1 className="page-title" style={{ marginBottom: 0 }}>
          Clientes
        </h1>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
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
          {canManageClients && (
            <button className="btn btn-primary" onClick={handleOpenCreate}>
              + Novo cliente
            </button>
          )}
        </div>
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
        {clients.length === 0 ? (
          <div className="empty">
            {temFiltroAplicado
              ? "Nenhum cliente encontrado com estes filtros. Tente limpar os filtros."
              : "Nenhum cliente cadastrado."}
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>CNPJ</th>
                <th>Contato</th>
                <th>Telefone</th>
                <th>E-mail</th>
                <th>Status</th>
                <th style={{ width: 260, textAlign: "right" }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <Fragment key={c.id}>
                  <tr key={c.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                        <button
                          type="button"
                          onClick={() => handleAbrirModalCliente(c.id)}
                          title="Abrir janela com impressoras e dados completos deste cliente"
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--primary)",
                            cursor: "pointer",
                            fontWeight: 600,
                            textAlign: "left",
                            padding: "0.2rem 0.35rem",
                            borderRadius: 6,
                            transition: "background .15s",
                          }}
                          onMouseEnter={(e) => {
                            (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-hover)";
                          }}
                          onMouseLeave={(e) => {
                            (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                          }}
                        >
                          <strong>{c.name}</strong>
                        </button>
                      </div>
                    </td>
                    <td>{c.cnpj || "—"}</td>
                    <td>{c.contact_name || "—"}</td>
                    <td>{c.contact_phone || "—"}</td>
                    <td>{c.contact_email || "—"}</td>
                    <td>
                      <span className={`badge ${c.active ? "online" : "offline"}`}>
                        {c.active ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {canManageClients && (
                        <>
                          <button
                            className="btn btn-secondary"
                            onClick={() => handleOpenEdit(c)}
                            style={{ marginRight: "0.35rem" }}
                          >
                            ✏️ Editar
                          </button>
                          <button
                            className="btn btn-ghost"
                            onClick={() => handleDelete(c.id, c.name)}
                            disabled={deletingClientId === c.id}
                            style={{ color: "var(--danger)" }}
                          >
                            {deletingClientId === c.id ? "Excluindo..." : "Excluir"}
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && canManageClients && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingClientId !== null ? "Editar cliente" : "Novo cliente"}</h3>
            <form onSubmit={handleSave}>
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
                <label>Telefone</label>
                <input placeholder="(11) 99999-0000" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} />
              </div>
              <div className="form-group">
                <label>E-mail</label>
                <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={handleCloseModal}>Cancelar</button>
                <button type="submit" className="btn btn-primary">Salvar</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {pairingClientId !== null && activePairingClient && (
        <div className="modal-overlay" onClick={closePairing}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 720 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", marginBottom: "1rem" }}>
              <div>
                <h3 style={{ marginTop: 0, marginBottom: "0.25rem" }}>Pós-instalação · Pareamento</h3>
                <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
                  Cliente: <strong style={{ color: "var(--text)" }}>{activePairingClient.name}</strong>
                </div>
              </div>
              <button className="btn btn-ghost" onClick={closePairing} aria-label="Fechar">✕</button>
            </div>

            {!pairingResult ? (
              <div>
                <p style={{ marginTop: 0, color: "var(--text-muted)" }}>
                  Gere um código de pareamento curto para o cliente usar no Wizard de instalação.
                  Esse código vincula automaticamente o agente (e todas as impressoras que ele encontrar)
                  a este cliente.
                </p>
                <div className="form-group">
                  <label>Nome do agente</label>
                  <input
                    value={pairingAgentName}
                    onChange={(e) => setPairingAgentName(e.target.value)}
                    placeholder="Ex.: Agente Loja Centro"
                  />
                </div>
                <div className="form-group">
                  <label>Validade do código (em minutos)</label>
                  <input
                    type="number"
                    min={1}
                    max={43200}
                    value={pairingTtl}
                    onChange={(e) => setPairingTtl(Number(e.target.value) || 0)}
                  />
                  <small style={{ color: "var(--text-muted)" }}>
                    60 = 1 hora · 1440 = 1 dia · 10080 = 1 semana · 43200 = 30 dias
                  </small>
                </div>

                {pairingError && (
                  <div style={{ background: "rgba(220,53,69,0.1)", color: "var(--danger)", padding: "0.55rem 0.8rem", borderRadius: 6, marginBottom: "1rem", fontSize: 14 }}>
                    Erro: {pairingError}
                  </div>
                )}

                <div className="modal-actions">
                  <button type="button" className="btn btn-ghost" onClick={closePairing}>Cancelar</button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={pairingLoading || !pairingAgentName.trim()}
                    onClick={doGeneratePairing}
                  >
                    {pairingLoading ? "Gerando..." : "🔐 Gerar código de pareamento"}
                  </button>
                </div>
              </div>
            ) : (
              <div>
                {/* Código de pareamento */}
                <div style={{
                  margin: "0.25rem 0 1rem",
                  padding: "1.25rem",
                  borderRadius: 10,
                  background:
                    "linear-gradient(135deg, rgba(32,128,240,0.14) 0%, rgba(32,128,240,0.06) 100%)",
                  border: "1px solid rgba(32,128,240,0.35)",
                }}>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: "0.35rem" }}>
                    Código de pareamento
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                    <div style={{
                      fontFamily: "'Courier New', ui-monospace, monospace",
                      fontSize: 34,
                      fontWeight: 800,
                      letterSpacing: 6,
                      color: "var(--primary)",
                      userSelect: "all",
                    }}>
                      {pairingResult.pairing_code}
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={doCopyPairingCode}
                    >
                      {pairingCopied ? "✓ Copiado" : "📋 Copiar código"}
                    </button>
                  </div>
                  <div style={{ marginTop: "0.75rem", fontSize: 13, color: "var(--text-muted)" }}>
                    Expira em: <strong style={{ color: "var(--text)" }}>{formatDateTimeBrasil(pairingResult.pairing_expires_at)}</strong>
                    {"  ·  "}
                    {pairingResult.server_url && (
                      <>Servidor: <code style={{ background: "rgba(0,0,0,0.08)", padding: "1px 6px", borderRadius: 4 }}>{pairingResult.server_url}</code></>
                    )}
                  </div>
                </div>

                {/* Mensagem pós-instalação para o cliente */}
                <div style={{
                  padding: "1rem 1.1rem",
                  borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                }}>
                  <div style={{ fontWeight: 700, fontSize: 15, marginBottom: "0.6rem" }}>
                    📩 Instruções para enviar ao cliente (copie e cole no WhatsApp / e-mail)
                  </div>
                  <div style={{ fontSize: 13.5, lineHeight: 1.55, whiteSpace: "pre-wrap", color: "var(--text)" }}>
{`Olá, tudo bem?

Estamos configurando o monitoramento automático das suas impressoras! 🖨️

Siga esses 3 passos no computador principal da empresa:

1️⃣ BAIXE o instalador no link oficial abaixo e dê DUPLA CLIQUE para instalar:
   🔗 ${INSTALLER_DOWNLOAD_URL}
2️⃣ Ao terminar a instalação, abrirá automaticamente um "Wizard de Pareamento".
3️⃣ Quando perguntar, informe:
     • URL do servidor: ${pairingInlineServerUrl()}
     • Código de pareamento: ${pairingResult.pairing_code}
     • Comunidade SNMP: public (só aperte Enter)

Pronto! 😊 Em menos de 2 minutos o sistema encontra sozinho todas as impressoras da sua rede e começa a monitorar nível de toner, contadores e alertas.
Qualquer dúvida é só chamar a gente!`}
                  </div>
                  <div style={{ marginTop: "0.75rem", textAlign: "right" }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        copyText(buildPairingMessage());
                      }}
                    >
                      📋 Copiar mensagem completa
                    </button>
                  </div>
                </div>

                {/* Dados para você / suporte */}
                <div style={{ marginTop: "0.85rem", fontSize: 12.5, color: "var(--text-muted)" }}>
                  <div>ℹ️ <strong>Dados internos:</strong> agent_id = {pairingResult.agent_id} · client_id = {pairingResult.client_id} · nome = {pairingResult.name}</div>
                </div>

                <div className="modal-actions" style={{ marginTop: "1.25rem" }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setPairingResult(null);
                      setPairingError(null);
                    }}
                  >
                    Gerar NOVO código
                  </button>
                  <button type="button" className="btn btn-primary" onClick={closePairing}>Fechar</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ============================================================
           MODAL NÍVEL 1: CLIENTE (lista impressoras dele)
           Julio pediu para ficar profissional = não inline, modal!
         ============================================================ */}
      {(() => {
        const clienteModal = clienteModalId ? clients.find((c) => c.id === clienteModalId) : null;
        if (!clienteModal) return null;
        return (
          <div className="modal-overlay" onClick={handleFecharModalCliente}>
            <div
              className="modal"
              onClick={(e) => e.stopPropagation()}
              style={{
                width: "calc(100% - 64px)",
                height: "calc(100vh - 96px)",
                maxWidth: "1880px",
                maxHeight: "calc(100vh - 96px)",
                minWidth: "720px",
                minHeight: "520px",
                display: "flex",
                flexDirection: "column",
                padding: 0,
                margin: 0,
                boxSizing: "border-box",
                position: "relative",
                flex: "0 1 auto",
              }}
            >
              {/* ===== HEADER MODAL CLIENTE ===== */}
              <div
                style={{
                  padding: "1.1rem 1.4rem",
                  borderBottom: "1px solid var(--border)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "1rem",
                  flexWrap: "wrap",
                  background: "var(--surface)",
                  position: "sticky",
                  top: 0,
                  zIndex: 2,
                }}
              >
                <div>
                  <h3 style={{ margin: 0, fontSize: "1.3rem", display: "flex", alignItems: "center", gap: 8 }}>
                    🏢 {clienteModal.name}
                    <span className={`badge ${clienteModal.active ? "online" : "offline"}`} style={{ marginLeft: 6 }}>
                      {clienteModal.active ? "Ativo" : "Inativo"}
                    </span>
                  </h3>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 4 }}>
                    {clienteModal.partner_name && <span>Parceiro: <strong style={{ color: "var(--text)" }}>{clienteModal.partner_name}</strong> · </span>}
                    ID #{clienteModal.id}
                  </div>

                  {/* ===== CODIGO DO CLIENTE EVIDENTISSIMO (Julio pediu para deixar AQUI no modal 1, nao mais na tabela!) ===== */}
                  {clienteModal.client_code && (
                    <div
                      style={{
                        marginTop: "0.9rem",
                        padding: "0.8rem 0.9rem",
                        borderRadius: 12,
                        background: "linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.05))",
                        border: "1.5px solid rgba(16,185,129,0.35)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "0.75rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: "0.75rem", color: "rgb(16,185,129)", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 3 }}>
                          🎫 Código do Cliente (usar para parear o agente!)
                        </div>
                        <div
                          style={{
                            fontFamily: "'Courier New', ui-monospace, monospace",
                            fontWeight: 900,
                            fontSize: "1.4rem",
                            color: "rgb(5,150,105)",
                            letterSpacing: 2.5,
                            padding: "0.15rem 0.25rem",
                            display: "inline-block",
                          }}
                        >
                          {clienteModal.client_code}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn btn-primary"
                          style={{
                            fontSize: 14,
                            padding: "0.5rem 0.9rem",
                            fontWeight: 700,
                            boxShadow: "0 3px 10px rgba(16,185,129,0.25)",
                          }}
                          onClick={() => copyText(clienteModal.client_code!)}
                        >
                          📋 Copiar Código
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ fontSize: 12, padding: "0.35rem 0.75rem" }}
                          onClick={() => { handleFecharModalCliente(); openPairing(clienteModal); }}
                        >
                          🔗 Gerar Pareamento (instalar agente)
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ fontSize: 12, padding: "0.35rem 0.75rem" }}
                          onClick={() => copyText(buildPairingMessage(clienteModal))}
                        >
                          📩 Copiar mensagem
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "flex-end", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ fontSize: 12, padding: "0.3rem 0.7rem" }}
                    onClick={() => handleAbrirModalCliente(clienteModal.id)}
                    disabled={loadingClienteModal}
                  >
                    {loadingClienteModal ? "Carregando…" : "🔄 Atualizar"}
                  </button>
                  <button className="btn btn-ghost" onClick={handleFecharModalCliente} title="Fechar">✕</button>
                </div>
              </div>

              {/* ===== CORPO: TABELA IMPRESSORAS (Sem titulo, Julio pediu para apagar!) ===== */}
              <div style={{ padding: "0.75rem 1.4rem", overflowY: "auto", flex: 1 }}>
                {loadingClienteModal ? (
                  <div className="loading" style={{ padding: "2rem 0" }}>Carregando impressoras…</div>
                ) : impressorasClienteModal.length === 0 ? (
                  <div style={{ color: "var(--text-muted)", padding: "1.5rem 1rem", textAlign: "center", border: "1px dashed var(--border)", borderRadius: 10 }}>
                    Nenhuma impressora encontrada para este cliente ainda.
                    <div style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
                      💡 Use o botão <strong>"🔗 Gerar Pareamento"</strong> na caixa verde acima (código do cliente) para criar um código curto e instalar o agente na máquina do cliente!
                    </div>
                  </div>
                ) : (
                  <table style={{ width: "100%" }}>
                    <thead>
                      <tr>
                        <th>🖨️ Impressora mapeada (clique para ver ficha completa)</th>
                        {canEditSector && <th style={{ width: 260, minWidth: 240 }}>📍 Setor / Local (clique para editar)</th>}
                        <th style={{ width: 160, textAlign: "center" }}>Ações</th>
                      </tr>
                    </thead>
                    <tbody>
                      {impressorasClienteModal.map((printer) => {
                        const isEditingSector = editingSectorPrinterId === printer.id;
                        const isSavingSector = savingSectorPrinterId === printer.id;
                        const currentSectorLabel = getPrinterSectorModal(printer);

                        return (
                          <tr key={printer.id}>
                            {/* ===== (1) MODELO CLICÁVEL (abre ModalPrinter) ===== */}
                            <td>
                              <button
                                type="button"
                                onClick={() => setPrinterModalId(printer.id)}
                                title="Abrir ficha completa: dados, IP, serial, toners, contadores total/PB/cor e últimas 30 leituras"
                                style={{
                                  background: "transparent",
                                  border: "none",
                                  padding: "0.9rem 1.1rem",
                                  margin: "-0.45rem -0.7rem",
                                  borderRadius: 10,
                                  cursor: "pointer",
                                  textAlign: "left",
                                  color: "var(--primary)",
                                  fontWeight: 700,
                                  fontSize: "1.05rem",
                                  width: "100%",
                                  transition: "background .15s",
                                }}
                                onMouseEnter={(e) => {
                                  (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-hover)";
                                }}
                                onMouseLeave={(e) => {
                                  (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                                }}
                              >
                                📄 {printer.model || "Impressora sem modelo cadastrado"}
                                {printer.manufacturer && (
                                  <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 400, marginTop: 3 }}>
                                    Fabricante: {printer.manufacturer}
                                    {printer.ip_address && (
                                      <>
                                        {" · "}
                                        <span title="Endereço IP (ver completo na ficha 2)">IP: {printer.ip_address}</span>
                                      </>
                                    )}
                                    {printer.serial_number && (
                                      <>
                                        {" · "}
                                        <span title="Número de série (ver completo na ficha 2)">Serial: {printer.serial_number}</span>
                                      </>
                                    )}
                                  </div>
                                )}
                              </button>
                            </td>

                            {/* ===== (2) SETOR EDITÁVEL (Julio pediu para trazer de volta para Modal 1!) ===== */}
                            {canEditSector && (
                              <td style={{ minWidth: 240 }}>
                                {isEditingSector ? (
                                  <select
                                    autoFocus
                                    disabled={isSavingSector}
                                    defaultValue={printer.location_id ? String(printer.location_id) : ""}
                                    style={{
                                      width: "100%",
                                      padding: "0.45rem 0.6rem",
                                      borderRadius: 8,
                                      border: "1.5px solid var(--primary)",
                                      background: "var(--surface)",
                                      color: "var(--text)",
                                      fontSize: 14,
                                      outline: "none",
                                    }}
                                    onBlur={() => setEditingSectorPrinterId(null)}
                                    onChange={async (evt) => {
                                      const value = evt.target.value;
                                      if (value === "prompt:new") {
                                        const nome = window.prompt("Digite o nome do novo setor / local:", "");
                                        if (!nome) {
                                          setEditingSectorPrinterId(null);
                                          return;
                                        }
                                        await handleChangeSectorModal(printer, `new:${nome}`);
                                      } else {
                                        await handleChangeSectorModal(printer, value);
                                      }
                                    }}
                                  >
                                    <option value="">❌ Sem setor / não definido</option>
                                    <optgroup label="Setores existentes">
                                      {locaisClienteModal.map((loc) => (
                                        <option key={loc.id} value={String(loc.id)}>
                                          {loc.sector || loc.name}
                                        </option>
                                      ))}
                                    </optgroup>
                                    <optgroup label="Ações">
                                      <option value="prompt:new">➕ Criar novo setor…</option>
                                    </optgroup>
                                  </select>
                                ) : (
                                  <button
                                    type="button"
                                    disabled={isSavingSector || !canEditSector}
                                    title={canEditSector ? "Clique para alterar o setor / local desta impressora" : "Sem permissão"}
                                    onClick={() => setEditingSectorPrinterId(printer.id)}
                                    style={{
                                      width: "100%",
                                      textAlign: "left",
                                      padding: "0.45rem 0.6rem",
                                      borderRadius: 8,
                                      border: "1.5px dashed transparent",
                                      background: "transparent",
                                      cursor: canEditSector ? "pointer" : "default",
                                      color: "var(--text)",
                                      fontSize: 14,
                                      fontWeight: 600,
                                      transition: "border-color .15s, background .15s",
                                    }}
                                    onMouseEnter={(e) => {
                                      if (canEditSector && !isSavingSector) {
                                        (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                                        (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)";
                                      }
                                    }}
                                    onMouseLeave={(e) => {
                                      (e.currentTarget as HTMLButtonElement).style.borderColor = "transparent";
                                      (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                                    }}
                                  >
                                    {isSavingSector ? "💾 Salvando…" : currentSectorLabel}
                                  </button>
                                )}
                              </td>
                            )}

                            {/* ===== (3) AÇÕES: BOTÃO REMOVER IMPRESSORA (Julio pediu para manter!) ===== */}
                            {canEditSector && (
                              <td style={{ textAlign: "center" }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  style={{
                                    color: "var(--danger)",
                                    borderColor: "transparent",
                                    background: "transparent",
                                    padding: "0.5rem 0.9rem",
                                    fontSize: 14,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 6,
                                  }}
                                  title="Remover esta impressora do monitoramento do cliente"
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
                                  onClick={() => handleRemovePrinterModal(printer)}
                                >
                                  🗑️ Remover
                                </button>
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* ============================================================
           MODAL NÍVEL 2: FICHA COMPLETA DA IMPRESSORA (Reutilizável)
           Usa componente ModalPrinter.tsx já criado profissionalmente!
         ============================================================ */}
      <ModalPrinter printerId={printerModalId} onClose={() => setPrinterModalId(null)} />
    </>
  );
}

/* ============ Helpers internos Clientes.tsx (antigos, sem uso) ============ */
