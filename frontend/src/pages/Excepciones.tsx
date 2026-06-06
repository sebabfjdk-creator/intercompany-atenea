import { useMemo, useState } from "react";
import { useFetch } from "../lib/useFetch";
import { fmtCOP, fmtPct, periodoLabel } from "../lib/format";
import { PageHeader, Card, DataState, CausaBadge } from "../components/ui";

interface Exc { grupo: string; tipo: string; periodo: string; total_co: number; total_es: number; diferencia: number; pct: number; causa: string | null }

export default function Excepciones() {
  const { data, loading, error, reload } = useFetch<Exc[]>("/api/excepciones");
  const [causa, setCausa] = useState("");
  const [periodo, setPeriodo] = useState("");
  const empty = !!data && data.length === 0;

  const causas = useMemo(() => [...new Set((data ?? []).map((e) => e.causa).filter(Boolean))] as string[], [data]);
  const periodos = useMemo(() => [...new Set((data ?? []).map((e) => e.periodo))], [data]);
  const filtered = (data ?? []).filter((e) => (!causa || e.causa === causa) && (!periodo || e.periodo === periodo));

  return (
    <div>
      <PageHeader title="Excepciones" subtitle="Diferencias que superan la tolerancia, ordenadas por magnitud" />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <Card>
            <div className="flex gap-3 mb-4">
              <select value={causa} onChange={(e) => setCausa(e.target.value)} className="border rounded px-3 py-2 text-sm">
                <option value="">Todas las causas</option>
                {causas.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={periodo} onChange={(e) => setPeriodo(e.target.value)} className="border rounded px-3 py-2 text-sm">
                <option value="">Todos los periodos</option>
                {periodos.map((p) => <option key={p} value={p}>{periodoLabel(p)}</option>)}
              </select>
              <span className="ml-auto text-sm text-slate-400 self-center">{filtered.length} excepciones</span>
            </div>
            <div className="overflow-x-auto max-h-[64vh]">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                  <tr><th className="text-left py-2">Grupo</th><th className="text-left">Periodo</th><th className="text-right">CO</th><th className="text-right">ES</th><th className="text-right">Diferencia</th><th className="text-right">%</th><th className="text-left pl-3">Causa</th></tr>
                </thead>
                <tbody>
                  {filtered.map((e, i) => (
                    <tr key={e.grupo + e.periodo + i} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="py-2 max-w-[240px] truncate" title={e.grupo}>{e.grupo} <span className="text-[10px] text-slate-400 uppercase">{e.tipo}</span></td>
                      <td>{periodoLabel(e.periodo)}</td>
                      <td className="text-right tabular-nums">{fmtCOP(e.total_co)}</td>
                      <td className="text-right tabular-nums">{fmtCOP(e.total_es)}</td>
                      <td className="text-right tabular-nums text-red-600 font-medium">{fmtCOP(e.diferencia)}</td>
                      <td className="text-right tabular-nums">{fmtPct(e.pct)}</td>
                      <td className="pl-3"><CausaBadge causa={e.causa} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </DataState>
    </div>
  );
}
