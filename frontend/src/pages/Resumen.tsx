import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Rubro { tipo: string; co: number; es: number; dif: number; grupos: number }
interface Resumen { rubros: Rubro[]; kpis: { conciliados: number; excepciones: number; dif_total_abs: number } }

export default function Resumen() {
  const { data, loading, error, reload } = useFetch<Resumen>("/api/resumen");
  const empty = !!data && data.rubros.length === 0;

  return (
    <div>
      <PageHeader title="Resumen por gran rubro" subtitle="Totales Colombia vs España y diferencias por tipo"
        action={<button onClick={() => descargarArchivo("/api/resumen/export", "resumen.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">⬇️ Excel</button>} />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Kpi label="Conciliados" value={data.kpis.conciliados} tone="green" />
              <Kpi label="Excepciones" value={data.kpis.excepciones} tone="red" />
              <Kpi label="Σ |Diferencias|" value={fmtCOP(data.kpis.dif_total_abs)} tone="amber" />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <Card title="CO vs ES por rubro">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={data.rubros}>
                    <XAxis dataKey="tipo" /><YAxis tickFormatter={(v) => `${(v / 1e6).toFixed(0)}M`} /><Tooltip formatter={(v: number) => fmtCOP(v)} /><Legend />
                    <Bar dataKey="co" name="Colombia" fill="#1565c0" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="es" name="España" fill="#c62828" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Detalle">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-slate-400">
                    <tr><th className="text-left py-2">Rubro</th><th className="text-right">Grupos</th><th className="text-right">CO</th><th className="text-right">ES</th><th className="text-right">Dif</th></tr>
                  </thead>
                  <tbody>
                    {data.rubros.map((r) => (
                      <tr key={r.tipo} className="border-t border-slate-100">
                        <td className="py-2 capitalize font-medium">{r.tipo}</td>
                        <td className="text-right">{r.grupos}</td>
                        <td className="text-right tabular-nums">{fmtCOP(r.co)}</td>
                        <td className="text-right tabular-nums">{fmtCOP(r.es)}</td>
                        <td className={`text-right tabular-nums ${Math.abs(r.dif) < 1000 ? "text-emerald-600" : "text-red-600"}`}>{fmtCOP(r.dif)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}
