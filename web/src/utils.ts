export const BR_TIMEZONE = "America/Sao_Paulo";

export function formatDateTimeBrasil(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const date = input instanceof Date ? input : new Date(input);
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
