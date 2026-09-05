// ========================================
// LOGOS OFICIAIS DO PRINT COLLECT (separadas por uso!)
// ========================================
// 1. LOGO_URL: Logo GENERICA do software Print Collect (USADA PELO SUPERADMIN DEPOIS QUE LOGA — no sidebar.
//    Antes era a C&A Solucoes; agora Julio separou as marcas:
//    Print Collect = plataforma/dono (superadmin)
//    CEA Copiadoras = revendedora (partner no banco)
// 2. PRINT_COLLECT_LOGO: a mesma SVG, exportada separadamente.
// ========================================

// Logo GENERICA do software Print Collect (SVG inline criada exclusivamente para o software:
// Simbolo: Impressora estilizada + ondas de conexao/sinal de coleta
// Nome: "Print Collect" (gradiente azul tech marinho -> ciano)
// Tagline: MONITORAMENTO AUTOMATICO
const SVG_SYMBOL = encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 120" width="420" height="120">
  <defs>
    <linearGradient id="pcGradientLogo" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1e3a8a"/>
      <stop offset="100%" stop-color="#06b6d4"/>
    </linearGradient>
    <linearGradient id="pcGradientAccent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#8b5cf6"/>
    </linearGradient>
  </defs>

  <!-- SIMBOLO: Caixa de impressora (azul gradiente) com folha saindo
       + ondas de sinal/conexao/rede (simbolo de "coletando contadores") -->
  <g transform="translate(12, 10)">
    <!-- Corpo principal da impressora -->
    <rect x="6" y="36" width="80" height="48" rx="8" ry="8"
          fill="url(#pcGradientLogo)" opacity="0.96"/>
    <!-- Bandeja de saida de papel (branca) -->
    <rect x="18" y="76" width="56" height="8" rx="3" fill="#ffffff" opacity="0.95"/>
    <!-- Folha saindo da impressora -->
    <rect x="26" y="20" width="40" height="24" rx="2" ry="2" fill="#ffffff" opacity="0.98"/>
    <!-- Linhas simulando texto na folha -->
    <rect x="32" y="26" width="28" height="2" rx="1" fill="#c7d2fe" opacity="0.9"/>
    <rect x="32" y="32" width="22" height="2" rx="1" fill="#c7d2fe" opacity="0.9"/>
    <!-- LED de status (verde = online/coletando) -->
    <circle cx="74" cy="60" r="4" fill="#10b981"/>
    <circle cx="74" cy="60" r="1.8" fill="#ffffff"/>

    <!-- Ondas de conexao/sinal (simbolo de coleta SNMP pela rede) -->
    <g transform="translate(92, 42)" fill="none" stroke="url(#pcGradientAccent)" stroke-width="3" stroke-linecap="round">
      <path d="M 4 18 Q 18 4 Q 32 18" />
      <path d="M 8 22 Q 20 10 Q 32 22" />
      <circle cx="18" cy="26" r="2.2" fill="url(#pcGradientAccent)"/>
    </g>
  </g>

  <!-- NOME DO SOFTWARE: "Print Collect" -->
  <g transform="translate(120, 44)">
    <text x="0" y="34"
          font-family="Segoe UI, Roboto, system-ui, sans-serif"
          font-size="32"
          font-weight="800"
          letter-spacing="-0.5"
          fill="#0f172a">Print</text>
    <text x="92" y="34"
          font-family="Segoe UI, Roboto, system-ui, sans-serif"
          font-size="32"
          font-weight="800"
          letter-spacing="-0.5"
          fill="url(#pcGradientLogo)">Collect</text>
    <!-- Tagline abaixo (pequena e elegante) -->
    <text x="0" y="56"
          font-family="Segoe UI, Roboto, system-ui, sans-serif"
          font-size="12"
          font-weight="500"
          letter-spacing="2"
          fill="#64748b">MONITORAMENTO  AUTOMATICO</text>
  </g>
</svg>`);

export const PRINT_COLLECT_LOGO = `data:image/svg+xml;charset=utf-8,${SVG_SYMBOL}`;

// 1) LOGO_URL = agora a mesma logo da plataforma (Print Collect), usada no fallback
//    do superadmin (sidebar) e na tela de login (PRINT_COLLECT_LOGO).
//    (mantida a exportacao LOGO_URL por compatibilidade com AuthContext antigo.)
export const LOGO_URL = PRINT_COLLECT_LOGO;
