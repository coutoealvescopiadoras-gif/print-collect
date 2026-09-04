export const BR_TIMEZONE = "America/Sao_Paulo";

/**
 * ✅ Helper modelo colorido CONFIRMADO (mesmas regras do backend routes.py!).
 * Retorna TRUE se modelo + fabricante PROVAM que é IMPRESSORA COLORIDA —
 * MESMO que toners CMY estejam NULL (ainda nao coletados) OU pages_color = 0 agora
 * (ex: KONICA bizhub C308 da Papelaria Exata com agente velho que nao detectou split).
 *
 * Julio pediu 100% confianca: NAO confia so na letra "c" isolada!
 *   Brother (HL-L3, MFC-L8 etc) | Epson (WF-C etc) | HP (Color LaserJet etc)
 *   Ricoh/Konica (MP C, bizhub C etc) | Kyocera (taskalfa etc)
 *   Xerox/Lexmark (VersaLink C, MC5 etc) | genericos ("color", "colorida" etc).
 */
export function modelConfirmadoColorido(
  model?: string | null | undefined,
  manufacturer?: string | null | undefined
): boolean {
  const text = `${manufacturer || ""} ${model || ""}`.toLowerCase().trim();
  if (!text) return false;

  // ===== Anti-falso-positivo RAPIDO: Ricoh P&B de verdade (NAO tem "C" depois do prefixo!)
  //   Ricoh MP 501   → P&B! (mp\s(?!c) = "mp" seguido ESPACO NAO "c"
  //   Ricoh SP 3710 → P&B!
  if (/ricoh/.test(text) && /\bmp\s(?!c)/.test(text)) return false;
  if (/ricoh/.test(text) && /\bsp\s(?!c)/.test(text)) return false;

  // ===== KEYWORDS COLORIDAS CONFIRMADAS (Julio pediu todas as marcas!) =====
  const colorKeywords: string[] = [
    // KONICA MINOLTA coloridas (padroes oficiais bizhub)
    "bizhub c",
    " c258",
    " c308",
    " c368",
    " c458",
    " c558",
    " c658",
    " c250",
    " c300",
    " c350",
    " c450",
    " c550",
    " c650",
    // RICOH coloridas (tem "C" DEPOIS do prefixo MP/IM/SP!)
    "mp c",
    "im c",
    "sp c",
    "ricoh mp c",
    "ricoh im c",
    "ricoh sp c",
    // KYOCERA coloridas
    "taskalfa",
    "ecosys m5",
    "ecosys m6",
    "ecosys m8",
    "ecosys p5",
    // BROTHER coloridas (series L3 / L8 / L9 = color!)
    "hl-l3",
    "dcp-l3",
    "mfc-l3",
    "hl-l8",
    "hl-l9",
    "mfc-l8",
    "mfc-l9",
    // SAMSUNG + HP COLOR LASER (linha color do HP!)
    "clp-",
    "clx-",
    "xpress c",
    "color laserjet",
    // XEROX coloridas
    "versalink c",
    "altalink c",
    "workcentre 6",
    "workcentre 7",
    "phaser 6",
    // LEXMARK coloridas
    "mc3",
    "mc4",
    "mc5",
    "mc6",
    // EPSON coloridas (WorkForce color = linha WF-C!)
    "wf-c",
    "workforce pro wf-c",
    "workforce c",
    // genericos (ultima camada)
    "color",
    "colorida",
    "impressora cor",
  ];

  return colorKeywords.some((k) => text.includes(k));
}

function normalizeToUtcIfUnspecified(input: string | Date): Date {
  if (input instanceof Date) return input;
  const trimmed = input.trim();
  const hasTimezoneIndicator =
    trimmed.endsWith("Z") ||
    trimmed.endsWith("z") ||
    /[+-]\d{2}:\d{2}$/.test(trimmed) ||
    /[+-]\d{4}$/.test(trimmed);
  if (hasTimezoneIndicator) return new Date(trimmed);
  if (trimmed.includes("T") || /\d{2}:\d{2}/.test(trimmed)) {
    return new Date(trimmed.endsWith("Z") ? trimmed : trimmed + "Z");
  }
  return new Date(trimmed);
}

export function formatDateTimeBrasil(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const date = normalizeToUtcIfUnspecified(input);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("pt-BR", {
    timeZone: BR_TIMEZONE,
    dateStyle: "short",
    timeStyle: "medium",
  });
}

export function formatNumberBrasil(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR");
}
