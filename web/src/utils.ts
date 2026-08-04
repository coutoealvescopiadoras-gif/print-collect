export const BR_TIMEZONE = "America/Sao_Paulo";

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
