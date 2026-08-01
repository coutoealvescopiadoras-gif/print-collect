import { Fragment, useEffect, useState } from "react";
import { api, getPublicApiUrl } from "../api";
import type { AgentPairingCode, Client, Location, Printer } from "../types";
import { useAuth } from "../context/AuthContext";

function formatDatePtBr(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR");
}

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
  const { user } = useAuth();
  const effectiveRole = user?.role || "superadmin";
  const canManageClients = effectiveRole === "superadmin" || effectiveRole === "partner_admin";
  const [clients, setClients] = useState<Client[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ name: "", cnpj: "", contact_name: "", contact_email: "" });
  const [deletingClientId, setDeletingClientId] = useState<number | null>(null);
  const [expandedClientId, setExpandedClientId] = useState<number | null>(null);
  const [clientPrinters, setClientPrinters] = useState<Record<number, Printer[]>>({});
  const [clientLocations, setClientLocations] = useState<Record<number, Location[]>>({});
  const [loadingPrintersClientId, setLoadingPrintersClientId] = useState<number | null>(null);

  // Modal pareamento
  const [pairingClientId, setPairingClientId] = useState<number | null>(null);
  const [pairingAgentName, setPairingAgentName] = useState("");
  const [pairingTtl, setPairingTtl] = useState(1440);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairingError, setPairingError] = useState<string | null>(null);
  const [pairingResult, setPairingResult] = useState<AgentPairingCode | null>(null);
  const [pairingCopied, setPairingCopied] = useState(false);

  const load = () => api.getClients().then(setClients);
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.createClient(form);
    setShowModal(false);
    setForm({ name: "", cnpj: "", contact_name: "", contact_email: "" });
    load();
  };

  const handleDelete = async (clientId: number, clientName: string) => {
    const ok = window.confirm(`Excluir o cliente "${clientName}"?\n\nIsso também apagará impressoras, leituras, alertas e agentes vinculados a ele.`);
    if (!ok) return;
    try {
      setDeletingClientId(clientId);
      await api.deleteClient(clientId);
      if (expandedClientId === clientId) {
        setExpandedClientId(null);
      }
      load();
    } finally {
      setDeletingClientId(null);
    }
  };

  const getPrinterSector = (clientId: number, printer: Printer) => {
    if (!printer.location_id) return "—";
    const location = (clientLocations[clientId] || []).find((item) => item.id === printer.location_id);
    return location ? (location.sector || location.name || "—") : "—";
  };

  const toggleClientPrinters = async (clientId: number) => {
    if (expandedClientId === clientId) {
      setExpandedClientId(null);
      return;
    }
    setExpandedClientId(clientId);
    if (clientPrinters[clientId]) return;
    try {
      setLoadingPrintersClientId(clientId);
      const [printers, locations] = await Promise.all([
        api.getPrinters(clientId),
        api.getLocations(clientId),
      ]);
      setClientPrinters((current) => ({ ...current, [clientId]: printers }));
      setClientLocations((current) => ({ ...current, [clientId]: locations }));
    } finally {
      setLoadingPrintersClientId(null);
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

  const buildPairingMessage = () => {
    const publicServerUrl = pairingResult?.server_url || getPublicApiUrl() || "https://www.printcollect.com.br";
    const code = pairingResult?.pairing_code ?? "<CODIGO-AQUI>";
    return [
      "Olá, tudo bem?",
      "",
      "Estamos configurando o monitoramento automático das suas impressoras! 🖨️",
      "",
      "Siga esses 3 passos no computador principal da empresa:",
      "",
      `1️⃣ BAIXE o instalador no link oficial abaixo e dê DUPLA CLIQUE para instalar:`,
      `   🔗 ${INSTALLER_DOWNLOAD_URL}`,
      "2️⃣ Ao terminar a instalação, abrirá automaticamente um \"Wizard de Pareamento\".",
      "3️⃣ Quando perguntar, informe:",
      `     • URL do servidor: ${publicServerUrl}`,
      `     • Código de pareamento: ${code}`,
      "     • Comunidade SNMP: public (só aperte Enter)",
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h1 className="page-title" style={{ marginBottom: 0 }}>Clientes</h1>
        {canManageClients && (
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Novo cliente</button>
        )}
      </div>

      <div className="card">
        {clients.length === 0 ? (
          <div className="empty">Nenhum cliente cadastrado</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>CNPJ</th>
                <th>Contato</th>
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
                          onClick={() => toggleClientPrinters(c.id)}
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--primary)",
                            cursor: "pointer",
                            fontWeight: 600,
                            textAlign: "left",
                            padding: 0,
                          }}
                        >
                          {expandedClientId === c.id ? "▼ " : "▶ "}{c.name}
                        </button>
                      </div>
                    </td>
                    <td>{c.cnpj || "—"}</td>
                    <td>{c.contact_name || "—"}</td>
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
                            onClick={() => openPairing(c)}
                            style={{ marginRight: "0.35rem" }}
                          >
                            🔗 Pareamento
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
                  {expandedClientId === c.id && (
                    <tr key={`details-${c.id}`}>
                      <td colSpan={6} style={{ background: "var(--surface-hover)" }}>
                        <div style={{ padding: "1rem 0" }}>
                          <div style={{ fontWeight: 600, marginBottom: "0.75rem" }}>
                            Impressoras mapeadas para {c.name}
                          </div>
                          {loadingPrintersClientId === c.id ? (
                            <div className="loading" style={{ padding: "0.5rem 0", textAlign: "left" }}>
                              Carregando impressoras...
                            </div>
                          ) : (clientPrinters[c.id] || []).length === 0 ? (
                            <div style={{ color: "var(--text-muted)" }}>
                              Nenhuma impressora encontrada para este cliente.{" "}
                              {canManageClients && (
                                <button
                                  className="btn btn-link"
                                  style={{ padding: 0, margin: 0 }}
                                  onClick={() => openPairing(c)}
                                >
                                  Gerar código de pareamento para instalar o agente.
                                </button>
                              )}
                            </div>
                          ) : (
                            <table>
                              <thead>
                                <tr>
                                  <th>Modelo</th>
                                  <th>Setor</th>
                                  <th>IP</th>
                                  <th>Serial</th>
                                  <th>Status</th>
                                  <th>Contador</th>
                                  <th>Última coleta</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(clientPrinters[c.id] || []).map((printer) => (
                                  <tr key={printer.id}>
                                    <td>
                                      <div>{printer.model || "—"}</div>
                                      {printer.manufacturer && (
                                        <small style={{ color: "var(--text-muted)" }}>{printer.manufacturer}</small>
                                      )}
                                    </td>
                                    <td>{getPrinterSector(c.id, printer)}</td>
                                    <td>{printer.ip_address}</td>
                                    <td>{printer.serial_number || "—"}</td>
                                    <td>
                                      <span className={`badge ${printer.status}`}>{printer.status}</span>
                                    </td>
                                    <td>{printer.pages_total.toLocaleString("pt-BR")}</td>
                                    <td>
                                      {printer.last_seen
                                        ? new Date(printer.last_seen).toLocaleString("pt-BR")
                                        : "—"}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && canManageClients && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Novo cliente</h3>
            <form onSubmit={handleCreate}>
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
                <label>E-mail</label>
                <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancelar</button>
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
                    Expira em: <strong style={{ color: "var(--text)" }}>{formatDatePtBr(pairingResult.pairing_expires_at)}</strong>
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
    </>
  );
}
