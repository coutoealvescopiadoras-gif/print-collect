import { useEffect, useState } from "react";
import { api } from "../api";

type InstallerInfo = {
  available: boolean;
  file_size_bytes: number;
  file_size_mb: number;
  version: string;
  built_at: string | null;
  download_url: string;
  note: string;
};

const INSTALLER_DOWNLOAD_URL_FALLBACK = "https://www.printcollect.com.br/PrintCollectSetup.exe";

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

export default function Instalador() {
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedMessage, setCopiedMessage] = useState(false);
  const [info, setInfo] = useState<InstallerInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const DOWNLOAD_URL = info?.available
    ? api.getInstallerDownloadUrl() || info.download_url
    : INSTALLER_DOWNLOAD_URL_FALLBACK;

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await api.getInstallerInfo();
        if (alive && data) setInfo(data);
      } catch (err) {
        if (alive) setInfo(null);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const TEMPLATE_MESSAGE = [
    "Olá, tudo bem?",
    "",
    "Estamos configurando o monitoramento automático das suas impressoras! 🖨️",
    "",
    "Siga esses 3 passos no computador principal da empresa (ou na filial):",
    "",
    `1️⃣ BAIXE o instalador no link oficial abaixo e dê DUPLA CLIQUE para instalar:`,
    `   🔗 ${DOWNLOAD_URL}`,
    "2️⃣ Ao terminar a instalação, abrirá automaticamente um \"Wizard de Instalação\".",
    "3️⃣ Quando perguntar, informe SEU CÓDIGO DO CLIENTE (não expira, sempre o mesmo):",
    "     • Código do Cliente: 🎫 <COLOQUE AQUI O CÓDIGO DO CLIENTE>",
    "     • Comunidade SNMP: public (só aperte Enter)",
    "",
    "💡 Dica: Instalou na matriz, e agora quer instalar também em outras 2 filiais da mesma empresa?",
    "       Basta rodar o instalador em cada filial e usar o MESMO CÓDIGO DO CLIENTE acima!",
    "       Todas as impressoras de todas as filiais ficarão cadastradas automaticamente na sua empresa.",
    "",
    "Pronto! 😊 Em menos de 2 minutos o sistema encontra sozinho todas as impressoras da sua rede e começa a monitorar nível de toner, contadores e alertas.",
    "Qualquer dúvida é só chamar a gente!",
  ].join("\n");

  return (
    <>
      <h1 className="page-title">📦 Instalador e Arquivos</h1>

      {/* ============================================================
          CARD 1: DOWNLOAD DO INSTALADOR WINDOWS
          ============================================================ */}
      <div className="card" style={{ marginBottom: "1.25rem", padding: "1.5rem 1.75rem", background: "linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(16,185,129,0.12) 100%)", border: "1px solid rgba(59,130,246,0.3)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1.25rem", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 420px", minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 18, marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.6rem" }}>
              💻 <span>Agente de Monitoramento — Instalador Windows (Universal 32/64 bits ✅)</span>
            </div>
            <div style={{ fontSize: 14.5, color: "var(--text-muted)", marginBottom: "1rem", lineHeight: 1.55 }}>
              Instale este executável no computador principal de cada cliente (ou em cada filial). O agente encontra automaticamente todas as impressoras da rede local e começa a enviar os dados de toner, contadores e status para o painel online.
              <br />
              <strong>Arquivo:</strong> <code style={{ fontSize: 12.5, padding: "1px 5px", borderRadius: 4, background: "rgba(255,255,255,0.06)" }}>PrintCollectSetup.exe</code>
              {!loading && info?.available ? (
                <>
                  <strong style={{ marginLeft: "0.8rem" }}>Tamanho:</strong> ~{info.file_size_mb} MB ·
                  <strong style={{ marginLeft: "0.8rem" }}>Versão:</strong> {info.version} ·
                  {info.built_at && (
                    <span>
                      <strong style={{ marginLeft: "0.8rem" }}>Buildado em:</strong> {new Date(info.built_at).toLocaleString("pt-BR")} ·
                    </span>
                  )}
                  <strong style={{ marginLeft: "0.4rem" }}>Plataforma:</strong> Windows 10/11 32/64 bits ou Windows Server 2016+
                </>
              ) : (
                <>
                  <strong style={{ marginLeft: "0.8rem" }}>Tamanho:</strong> ~12-15 MB ·
                  <strong style={{ marginLeft: "0.8rem" }}>Plataforma:</strong> Windows 10/11 32/64 bits ou Windows Server 2016+
                </>
              )}
            </div>

            {/* Aviso SE Setup NAO estiver disponivel ainda */}
            {!loading && info && !info.available && (
              <div style={{
                marginBottom: "1rem",
                padding: "0.7rem 1rem",
                borderRadius: 10,
                background: "rgba(245, 158, 11, 0.1)",
                border: "1px solid rgba(245, 158, 11, 0.3)",
                color: "#fbbf24",
                fontSize: 14,
              }}>
                ⚠️ <strong style={{ color: "#fbbf24" }}>Aviso:</strong> {info.note}
                <br />
                <span style={{ fontSize: 13, color: "#fcd34d" }}>
                  Rode o workflow <code style={{ background: "rgba(0,0,0,0.2)", padding: "1px 5px", borderRadius: 4 }}>Build Print Collect Setup (Windows x86 32-bit Universal)</code> na aba <strong>Actions</strong> do seu repositório GitHub. O build leva ~5 minutos.
                </span>
              </div>
            )}

            <div style={{
              display: "flex", alignItems: "center", gap: "0.7rem", flexWrap: "wrap",
              padding: "0.7rem 0.9rem", borderRadius: 10,
              background: "var(--surface)", border: "1px solid var(--border)",
            }}>
              <a
                href={DOWNLOAD_URL}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontFamily: "'Courier New', ui-monospace, monospace",
                  fontSize: 13, color: "var(--primary)",
                  textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis",
                  whiteSpace: "nowrap", flex: "1 1 300px", minWidth: 0,
                }}
                title={DOWNLOAD_URL}
              >
                {DOWNLOAD_URL}
              </a>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => { copyText(DOWNLOAD_URL); setCopiedLink(true); setTimeout(() => setCopiedLink(false), 2000); }}
              >
                {copiedLink ? "✓ Link copiado!" : "📋 Copiar link"}
              </button>
              <a
                href={DOWNLOAD_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary"
                style={{ padding: "0.55rem 1.2rem", fontSize: 15, fontWeight: 600, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
              >
                ⬇️ <span>Baixar Instalador</span>
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================
          CARD 2: COMO DESBLOQUEAR O EXE (WINDOWS SMARTSCREEN)
          ============================================================ */}
      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <div className="card-header">
          <h2 style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.55rem" }}>
            🛡️ <span>Arquivo bloqueado no Windows? Veja como desbloquear</span>
          </h2>
        </div>
        <div style={{ padding: "0.5rem 1.25rem 1rem" }}>
          <p style={{ color: "var(--text-muted)", marginBottom: "1rem", marginTop: "0.5rem" }}>
            É normal o Windows SmartScreen ou o Microsoft Defender bloquearem arquivos .exe baixados da internet que ainda não têm certificado de assinatura digital. Basta seguir um dos passos abaixo:
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1rem" }}>
            {/* Passo a passo 1: Propriedades -> Desbloquear */}
            <div style={{ padding: "1rem 1.25rem", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)" }}>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: "0.75rem", color: "var(--primary)" }}>
                Método 1 · Propriedades do Arquivo (Recomendado)
              </div>
              <ol style={{ paddingLeft: "1.25rem", margin: 0, lineHeight: 1.8, fontSize: 14, color: "var(--text)" }}>
                <li>Abra a pasta <strong>Downloads</strong> do Windows Explorer.</li>
                <li>Clique com o <strong>botão direito</strong> no <code>PrintCollectSetup.exe</code>.</li>
                <li>Escolha a opção <strong>Propriedades</strong>.</li>
                <li>No rodapé da janela, marque a caixa <strong>✅ Desbloquear</strong>.</li>
                <li>Clique em <strong>Aplicar</strong> e depois <strong>OK</strong>.</li>
                <li>Dê <strong>duplo clique</strong> no instalador — funciona!</li>
              </ol>
            </div>

            {/* Passo a passo 2: Navegador */}
            <div style={{ padding: "1rem 1.25rem", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)" }}>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: "0.75rem", color: "var(--primary)" }}>
                Método 2 · Direto no Navegador (Chrome/Edge)
              </div>
              <ol style={{ paddingLeft: "1.25rem", margin: 0, lineHeight: 1.8, fontSize: 14, color: "var(--text)" }}>
                <li>Após o download, clique no <strong>ícone de seta</strong> ao lado do arquivo no painel de downloads.</li>
                <li>Se aparecer <em>"Este arquivo não é baixado com frequência"</em>, clique em <strong>Mostrar mais → Manter mesmo assim</strong>.</li>
                <li>Depois clique em <strong>Abrir arquivo</strong>.</li>
                <li>Se aparecer <em>"Windows protegeu seu computador"</em>, clique em <strong>Mais informações → Executar assim mesmo</strong>.</li>
              </ol>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================
          CARD 3: MENSAGEM WHATSAPP MODELO PRONTA
          ============================================================ */}
      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <div className="card-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.55rem" }}>
            💬 <span>Mensagem WhatsApp · Modelo Pronto</span>
          </h2>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => { copyText(TEMPLATE_MESSAGE); setCopiedMessage(true); setTimeout(() => setCopiedMessage(false), 2000); }}
          >
            {copiedMessage ? "✓ Mensagem copiada!" : "📋 Copiar modelo"}
          </button>
        </div>
        <div style={{ padding: "0 1.25rem 1rem" }}>
          <p style={{ color: "var(--text-muted)", marginTop: "0.5rem", marginBottom: "0.8rem", fontSize: 14 }}>
            Use este modelo de mensagem para enviar para cada cliente por WhatsApp ou e-mail. Lembre-se de <strong>trocar <code style={{ fontSize: 12, padding: "1px 5px", borderRadius: 4, background: "rgba(255,255,255,0.06)" }}>&lt;COLOQUE AQUI O CÓDIGO DO CLIENTE&gt;</code></strong> pelo código de 8 dígitos do cliente (gerado automaticamente ao cadastrar na aba Clientes).
          </p>
          <pre style={{
            margin: 0, padding: "1rem 1.1rem",
            borderRadius: 10,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            fontSize: 13, lineHeight: 1.7,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
            color: "var(--text)",
            fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif",
          }}>
{TEMPLATE_MESSAGE}
          </pre>
        </div>
      </div>

      {/* ============================================================
          CARD 4: REQUISITOS MÍNIMOS
          ============================================================ */}
      <div className="card">
        <div className="card-header">
          <h2 style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.55rem" }}>
            ℹ️ <span>Requisitos e Informações</span>
          </h2>
        </div>
        <div style={{ padding: "0.5rem 1.25rem 1rem" }}>
          <table style={{ marginBottom: 0 }}>
            <tbody>
              <tr>
                <td style={{ width: 220, fontWeight: 600, color: "var(--text-muted)" }}>Sistema Operacional</td>
                <td>Windows 10 22H2 (64 bits), Windows 11, Windows Server 2016, 2019 ou 2022.</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--text-muted)" }}>Memória RAM</td>
                <td>Mínimo de 2 GB RAM livre (recomendado 4 GB).</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--text-muted)" }}>Espaço em Disco</td>
                <td>~80 MB após instalação completa (instalador ~12,7 MB).</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--text-muted)" }}>Rede</td>
                <td>
                  Conexão com a internet HTTPS (porta 443) para enviar dados ao painel.
                  <br />
                  Acesso de leitura SNMP (porta 161 UDP / comunidade padrão <code>public</code>) às impressoras da rede local.
                </td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--text-muted)" }}>Permissões de Instalação</td>
                <td>
                  Necessita de privilégios de <strong>Administrador Local</strong> apenas durante a instalação (para configurar inicialização automática do serviço com o Windows).
                  <br />
                  Depois de instalado, o agente roda em segundo plano como serviço do Windows, sem precisar de usuário logado.
                </td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--text-muted)" }}>Inicialização Automática</td>
                <td>✅ Sim. O instalador já configura para iniciar automaticamente com o Windows.</td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600, color: "var(--text-muted)" }}>Mesmo código para várias filiais?</td>
                <td>✅ Sim! Todas as filiais do MESMO CLIENTE usam o mesmo 🎫 Código do Cliente (não expira, sempre igual).</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
