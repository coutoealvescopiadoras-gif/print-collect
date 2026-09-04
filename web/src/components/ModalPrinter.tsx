import { useEffect, useState } from "react";
import { api } from "../api";
import type { Printer, Reading } from "../types";
import { formatDateTimeBrasil, formatNumberBrasil } from "../utils";

interface Props {
  printerId: number | null;
  onClose: () => void;
}

/**
 * FICHA COMPLETA DA IMPRESSORA (Modal Profissional Julio pediu!)
 *   Abre sempre no centro (modal-overlay + modal existente no CSS index.css).
 *   - Dados da impressora (modelo, cliente, setor, IP, serial, status, ultima coleta)
 *   - Contadores (Total / PB / Cor)
 *   - 4 Toners (Preto / Ciano / Magenta / Amarelo)
 *   - Tabela HISTORICO com as últimas 50 leituras (Readings)
 */
export default function ModalPrinter({ printerId, onClose }: Props) {
  const [printer, setPrinter] = useState<Printer | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!printerId) {
      setPrinter(null);
      setReadings([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [p, rs] = await Promise.all([
          api.getPrinterById(printerId),
          api.getPrinterReadings(printerId, 30),
        ]);
        if (cancelled) return;
        setPrinter(p);
        setReadings(rs || []);
      } catch (e: any) {
        if (cancelled) return;
        setError((e?.message || String(e)).slice(0, 200));
        setPrinter(null);
        setReadings([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [printerId]);

  if (!printerId) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
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
        <div
          style={{
            padding: "1.25rem 1.5rem",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            position: "sticky",
            top: 0,
            background: "var(--surface)",
            zIndex: 2,
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: "1.3rem", display: "flex", alignItems: "center", gap: 10 }}>
              🖨️ {printer?.model || "(Impressora sem nome)"}
              <span className={`badge ${printer?.status || "unknown"}`} style={{ marginLeft: 8 }}>
                {printer?.status || "—"}
              </span>
            </h3>
            <div style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 4 }}>
              Cliente: <strong>{printer?.client_name || "—"}</strong>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            title="Fechar"
            aria-label="Fechar"
          >
            ✕ Fechar
          </button>
        </div>

        <div style={{ padding: "1.25rem 1.5rem", overflowY: "auto" }}>
          {loading && <div style={{ padding: "3rem 0", textAlign: "center" }}>Carregando ficha da impressora…</div>}
          {!loading && error && (
            <div
              style={{
                padding: "0.9rem 1rem",
                borderRadius: 8,
                background: "rgba(239,68,68,0.08)",
                color: "var(--danger)",
                border: "1px solid rgba(239,68,68,0.25)",
              }}
            >
              Erro ao carregar: {error}
            </div>
          )}
          {!loading && !error && printer && (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: 12,
                  marginBottom: "1.25rem",
                }}
              >
                <InfoCard label="IP" value={<code>{printer.ip_address}</code>} />
                <InfoCard
                  label="Serial"
                  value={
                    printer.serial_number ? (
                      <code>{printer.serial_number}</code>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )
                  }
                />
                <InfoCard
                  label="Fabricante"
                  value={printer.manufacturer || <span style={{ color: "var(--text-muted)" }}>—</span>}
                />
                <InfoCard
                  label="Última coleta"
                  value={
                    printer.last_seen ? (
                      formatDateTimeBrasil(printer.last_seen)
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>Nunca</span>
                    )
                  }
                />
                <InfoCard
                  label="Cadastrada em"
                  value={formatDateTimeBrasil(printer.created_at)}
                />
              </div>

              {/* ==================== CONTADORES ==================== */}
              <div style={{ marginBottom: "1.25rem" }}>
                <h4 style={{ margin: "0 0 0.6rem 0" }}>📊 Contadores de páginas</h4>
                <ContadoresPrinter printer={printer} />
              </div>

              {/* ==================== TONERS (PB = só preto; COLOR = 4) ==================== */}
              {(() => {
                const isColor =
                  !!printer.toner_cyan ||
                  !!printer.toner_magenta ||
                  !!printer.toner_yellow ||
                  Number(printer.pages_color || 0) > 0;
                return (
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h4 style={{ margin: "0 0 0.6rem 0" }}>
                      🧪 Toners
                      <span style={{ fontWeight: 400, fontSize: "0.85rem", color: "var(--text-muted)", marginLeft: 8 }}>
                        ({isColor ? "Impressora COLORIDA - 4 cartuchos" : "Impressora PRETA & BRANCA - apenas toner preto"})
                      </span>
                    </h4>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: isColor
                          ? "repeat(auto-fit, minmax(200px, 1fr))"
                          : "repeat(auto-fit, minmax(220px, 320px))",
                        gap: 12,
                      }}
                    >
                      <TonerPB label="Preto" value={printer.toner_black} color="#111827" />
                      {isColor && (
                        <>
                          <TonerPB label="Ciano" value={printer.toner_cyan} color="#0891b2" />
                          <TonerPB label="Magenta" value={printer.toner_magenta} color="#db2777" />
                          <TonerPB label="Amarelo" value={printer.toner_yellow} color="#ca8a04" />
                        </>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* ==================== HISTORICO LEITURAS (1a COLETA POR DIA, MAX 30 DIAS MAIS NOVOS) ==================== */}
              {(() => {
                const isColor =
                  !!printer.toner_cyan ||
                  !!printer.toner_magenta ||
                  !!printer.toner_yellow ||
                  Number(printer.pages_color || 0) > 0;
                const dailyReadings = getPrimeiraLeituraPorDiaLimit30(readings);
                return (
                  <div>
                    <h4 style={{ margin: "0 0 0.6rem 0" }}>
                      🕒 Histórico de leituras
                      <span style={{ fontWeight: 400, fontSize: "0.85rem", color: "var(--text-muted)", marginLeft: 8 }}>
                        (primeira coleta de cada dia · {dailyReadings.length} dias)
                      </span>
                    </h4>
                    {dailyReadings.length === 0 ? (
                      <div className="empty">Nenhuma leitura registrada ainda (ainda não houve coleta para esta impressora).</div>
                    ) : (
                      <table style={{ width: "100%" }}>
                        <thead>
                          <tr>
                            <th>Data / Hora</th>
                            <th>Total</th>
                            {isColor && <th>PEB</th>}
                            {isColor && <th>Cor</th>}
                            <th style={{ textAlign: "center" }}>🖤</th>
                            {isColor && <th style={{ textAlign: "center" }}>🔵</th>}
                            {isColor && <th style={{ textAlign: "center" }}>🟣</th>}
                            {isColor && <th style={{ textAlign: "center" }}>🟡</th>}
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dailyReadings.map((r, idx) => {
                            const prev = dailyReadings[idx + 1];
                            const diffPages =
                              prev && r.pages_total >= prev.pages_total ? r.pages_total - prev.pages_total : null;
                            return (
                              <tr key={r.id}>
                                <td>{formatDateTimeBrasil(r.collected_at)}</td>
                                <td>
                                  <strong>{formatNumberBrasil(r.pages_total)}</strong>
                                  {diffPages !== null && diffPages > 0 && (
                                    <span style={{ color: "var(--success)", fontSize: "0.75rem", marginLeft: 4 }}>
                                      +{formatNumberBrasil(diffPages)}
                                    </span>
                                  )}
                                </td>
                                {isColor && <td>{formatNumberBrasil(r.pages_bw)}</td>}
                                {isColor && <td style={{ color: "var(--primary)" }}>{formatNumberBrasil(r.pages_color)}</td>}
                                <TDToner v={r.toner_black} />
                                {isColor && <TDToner v={r.toner_cyan} />}
                                {isColor && <TDToner v={r.toner_magenta} />}
                                {isColor && <TDToner v={r.toner_yellow} />}
                                <td>
                                  <span className={`badge ${r.status}`}>{r.status}</span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    )}
                  </div>
                );
              })()}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ==========================================================================
   Helpers internos
   ========================================================================== */

function InfoCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        background: "var(--surface-muted)",
        borderRadius: 10,
        padding: "0.75rem 0.9rem",
        border: "1px solid var(--border)",
      }}
    >
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{value}</div>
    </div>
  );
}

function ContadoresPrinter({ printer }: { printer: Printer }) {
  const isColor =
    !!printer.toner_cyan || !!printer.toner_magenta || !!printer.toner_yellow || Number(printer.pages_color || 0) > 0;
  const rawTotal = Number(printer.pages_total || 0);
  const pb = Number(printer.pages_bw || 0);
  const cor = Number(printer.pages_color || 0);
  const total = isColor ? Math.max(rawTotal, pb + cor) : rawTotal;

  if (!isColor) {
    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: 12,
        }}
      >
        <CardCounter label="Total" value={formatNumberBrasil(total)} accent="#0f172a" sub={"Páginas"} />
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
        gap: 12,
      }}
    >
      <CardCounter label="Total PEB" value={formatNumberBrasil(pb)} accent="#4b5563" sub={"Páginas"} />
      <CardCounter label="Total Coloridas" value={formatNumberBrasil(cor)} accent="#2563eb" sub={""} />
      <CardCounter label="Total Geral" value={formatNumberBrasil(total)} accent="#0f172a" sub={"PEB + Coloridas"} />
    </div>
  );
}

function CardCounter({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: string;
  accent: string;
  sub?: string;
}) {
  return (
    <div
      style={{
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: `linear-gradient(135deg, ${accent}10 0%, transparent 100%), var(--surface)`,
        borderTop: `3px solid ${accent}`,
        padding: "0.9rem 1rem",
      }}
    >
      <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: accent }}>{value}</div>
      {sub && <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function TonerPB({ label, value, color }: { label: string; value: number | null | undefined; color: string }) {
  const v = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  return (
    <div
      style={{
        borderRadius: 10,
        padding: "0.7rem 0.85rem",
        border: "1px solid var(--border)",
        background: "var(--surface-muted)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: color,
              display: "inline-block",
              border: "1px solid rgba(0,0,0,0.15)",
            }}
          />
          {label}
        </div>
        <span style={{ color: v === null ? "var(--text-muted)" : "inherit", fontSize: "0.85rem" }}>
          {v === null ? "—" : `${v}%`}
        </span>
      </div>
      {v !== null && (
        <div
          style={{
            width: "100%",
            height: 6,
            borderRadius: 3,
            background: "rgba(0,0,0,0.08)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${v}%`,
              height: "100%",
              background: color,
              transition: "width .3s ease",
            }}
          />
        </div>
      )}
    </div>
  );
}

function getPrimeiraLeituraPorDiaLimit30(readings: Reading[]): Reading[] {
  if (!readings || readings.length === 0) return [];
  const grupos: Record<string, Reading> = {};
  readings.forEach(r => {
    if (!r.collected_at) return;
    const data = new Date(r.collected_at);
    if (isNaN(data.getTime())) return;
    const chave = `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
    if (!grupos[chave]) {
      grupos[chave] = r;
    } else {
      const existente = new Date(grupos[chave].collected_at!).getTime();
      const novo = data.getTime();
      if (novo < existente) {
        grupos[chave] = r;
      }
    }
  });
  return Object.values(grupos)
    .sort((a, b) => new Date(b.collected_at!).getTime() - new Date(a.collected_at!).getTime())
    .slice(0, 30);
}

function TDToner({ v }: { v: number | null | undefined }) {
  const num = typeof v === "number" ? Math.max(0, Math.min(100, v)) : null;
  return (
    <td style={{ textAlign: "center" }}>
      {num === null ? (
        <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>—</span>
      ) : (
        <span
          style={{
            fontWeight: 600,
            color:
              num <= 10
                ? "var(--danger)"
                : num <= 25
                  ? "#ca8a04"
                  : "var(--text)",
            fontSize: "0.85rem",
          }}
        >
          {num}%
        </span>
      )}
    </td>
  );
}
