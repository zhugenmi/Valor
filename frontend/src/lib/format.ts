export function formatMoney(
  value: string | number,
  opts: { digits?: number; currency?: string } = {},
): string {
  const { digits = 2, currency = "¥" } = opts;
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "-";
  return `${currency}${n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatPnlClass(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n) || n === 0) return "";
  return n > 0 ? "text-red-500" : "text-green-500";
}

export function formatPercent(value: number, digits = 2): string {
  if (Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}
