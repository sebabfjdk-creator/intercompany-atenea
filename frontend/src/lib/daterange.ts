// Rangos rápidos para el date picker AR/AP. Fechas en ISO (YYYY-MM-DD).
const iso = (d: Date) => d.toISOString().slice(0, 10);

export function rangoChip(chip: string): { desde: string; hasta: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  switch (chip) {
    case "mes_actual":
      return { desde: iso(new Date(y, m, 1)), hasta: iso(new Date(y, m + 1, 0)) };
    case "mes_anterior":
      return { desde: iso(new Date(y, m - 1, 1)), hasta: iso(new Date(y, m, 0)) };
    case "trimestre": {
      const qStart = Math.floor(m / 3) * 3;
      return { desde: iso(new Date(y, qStart, 1)), hasta: iso(new Date(y, qStart + 3, 0)) };
    }
    case "anio":
      return { desde: iso(new Date(y, 0, 1)), hasta: iso(new Date(y, 11, 31)) };
    default:
      return { desde: "", hasta: "" };
  }
}

export const fmtFecha = (s: string | null) => {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
  return `${String(d.getDate()).padStart(2, "0")}/${meses[d.getMonth()]}/${d.getFullYear()}`;
};
