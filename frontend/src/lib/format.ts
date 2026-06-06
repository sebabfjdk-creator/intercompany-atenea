const cop = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});
const cop2 = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });

export const fmtCOP = (n: number | null | undefined) =>
  n == null ? "—" : cop.format(n);

export const fmtNum = (n: number | null | undefined) =>
  n == null ? "—" : cop2.format(n);

export const fmtPct = (n: number | null | undefined) =>
  n == null ? "—" : `${(n * 100).toFixed(2)}%`;

export const periodoLabel = (p: string) =>
  ({ "2026-01": "Enero", "2026-02-03": "Feb–Mar" } as Record<string, string>)[p] ?? p;
