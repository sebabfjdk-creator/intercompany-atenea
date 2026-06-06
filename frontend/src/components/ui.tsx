import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{title}</h1>
        {subtitle && <p className="text-slate-500 text-sm mt-1">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Kpi({ label, value, hint, tone = "slate" }: { label: string; value: ReactNode; hint?: string; tone?: "slate" | "green" | "red" | "blue" | "amber" }) {
  const tones: Record<string, string> = {
    slate: "text-slate-800",
    green: "text-emerald-600",
    red: "text-red-600",
    blue: "text-co",
    amber: "text-amber-600",
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${tones[tone]}`}>{value}</div>
      {hint && <div className="text-xs text-slate-400 mt-1">{hint}</div>}
    </div>
  );
}

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 shadow-sm ${className}`}>
      {title && <div className="px-4 py-3 border-b border-slate-100 font-semibold text-slate-700">{title}</div>}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function EstadoBadge({ estado }: { estado: string }) {
  const map: Record<string, string> = {
    conciliado: "bg-emerald-100 text-emerald-700",
    excepcion: "bg-red-100 text-red-700",
    en_revision: "bg-amber-100 text-amber-700",
    aprobado: "bg-blue-100 text-blue-700",
    con_observacion: "bg-purple-100 text-purple-700",
  };
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[estado] ?? "bg-slate-100 text-slate-600"}`}>{estado}</span>;
}

export function CausaBadge({ causa }: { causa: string | null }) {
  if (!causa) return null;
  const labels: Record<string, string> = {
    parafiscal_co: "Parafiscal CO",
    sin_homologar: "Sin homologar",
    redondeo: "Redondeo",
    timing: "Timing",
  };
  return <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600">{labels[causa] ?? causa}</span>;
}

export function DataState({ loading, error, empty, onRetry, children }: { loading: boolean; error?: string | null; empty?: boolean; onRetry?: () => void; children: ReactNode }) {
  if (loading) return <div className="py-16 text-center text-slate-400">Cargando…</div>;
  if (error)
    return (
      <div className="py-16 text-center">
        <p className="text-red-600">{error}</p>
        {onRetry && <button onClick={onRetry} className="mt-3 px-3 py-1.5 text-sm bg-slate-800 text-white rounded">Reintentar</button>}
      </div>
    );
  if (empty)
    return (
      <div className="py-16 text-center text-slate-400">
        No hay datos todavía. Sube los archivos en la página <b>Ingesta</b>.
      </div>
    );
  return <>{children}</>;
}
