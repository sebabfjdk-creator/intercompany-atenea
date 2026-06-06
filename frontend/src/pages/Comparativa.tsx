import { useFetch } from "../lib/useFetch";
import { fmtCOP, periodoLabel } from "../lib/format";
import { PageHeader, Kpi, Card, DataState, EstadoBadge, CausaBadge } from "../components/ui";

interface Celda { co: number; es: number; dif: number; pct: number; estado: string; causa: string | null }
interface Fila { grupo: string; tipo: string; celdas: Record<string, Celda>; total_co: number; total_es: number; total_dif: number }
interface Comp {
  periodos: string[];
  filas: Fila[];
  kpis: { grupos: number; cruces: number; conciliados: number; excepciones: number; dif_total_abs: number };
}

export default function Comparativa() {
  const { data, loading, error, reload } = useFetch<Comp>("/api/comparativa");
  const empty = !!data && data.filas.length === 0;

  return (
    <div>
      <PageHeader title="Comparativa PYG" subtitle="Total Colombia vs cuentas España, con diferencia por periodo (réplica del bosquejo)" />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <Kpi label="Grupos" value={data.kpis.grupos} tone="blue" />
              <Kpi label="Conciliados" value={data.kpis.conciliados} tone="green" />
              <Kpi label="Excepciones" value={data.kpis.excepciones} tone="red" />
              <Kpi label="Σ |Diferencias|" value={fmtCOP(data.kpis.dif_total_abs)} tone="amber" />
            </div>
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                    <tr>
                      <th className="text-left px-3 py-2 sticky left-0 bg-slate-50">Grupo</th>
                      {data.periodos.map((p) => (
                        <th key={p} className="text-right px-3 py-2" colSpan={3}>{periodoLabel(p)}</th>
                      ))}
                    </tr>
                    <tr className="text-[10px]">
                      <th className="sticky left-0 bg-slate-50"></th>
                      {data.periodos.flatMap((p) => [
                        <th key={p + "co"} className="text-right px-3 py-1 text-co">CO</th>,
                        <th key={p + "es"} className="text-right px-3 py-1 text-es">ES</th>,
                        <th key={p + "d"} className="text-right px-3 py-1">Dif</th>,
                      ])}
                    </tr>
                  </thead>
                  <tbody>
                    {data.filas.map((f, i) => (
                      <tr key={f.grupo + i} className="border-t border-slate-100 hover:bg-slate-50">
                        <td className="px-3 py-2 sticky left-0 bg-white">
                          <div className="font-medium text-slate-700 max-w-[220px] truncate" title={f.grupo}>{f.grupo}</div>
                          <span className="text-[10px] text-slate-400 uppercase">{f.tipo}</span>
                        </td>
                        {data.periodos.map((p) => {
                          const c = f.celdas[p];
                          if (!c) return <td key={p} colSpan={3} className="text-center text-slate-300">—</td>;
                          return [
                            <td key={p + "co"} className="text-right px-3 py-2 tabular-nums">{fmtCOP(c.co)}</td>,
                            <td key={p + "es"} className="text-right px-3 py-2 tabular-nums">{fmtCOP(c.es)}</td>,
                            <td key={p + "d"} className={`text-right px-3 py-2 tabular-nums ${c.estado === "conciliado" ? "text-emerald-600" : "text-red-600 font-medium"}`}>
                              <div className="flex items-center justify-end gap-1">
                                {fmtCOP(c.dif)}
                                <EstadoBadge estado={c.estado} />
                              </div>
                              {c.causa && <div className="text-right"><CausaBadge causa={c.causa} /></div>}
                            </td>,
                          ];
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <p className="text-xs text-slate-400 mt-3">
              CO = Colombia (Siesa) · ES = España (DELSOL). Tolerancia conciliación: |dif| ≤ $1.000 COP o ≤ 0,5%.
            </p>
          </>
        )}
      </DataState>
    </div>
  );
}
