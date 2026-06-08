import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Grupo { grupo: string; tipo: string; diferencia: number; z: number }
interface Cuenta { pais: string; codigo: string; nombre: string; valor: number }
interface Resp { sin_homologar: Cuenta[]; grupos_atipicos: Grupo[]; periodos: string[]; nota_zscore: string; kpis: { sin_homologar: number; grupos_atipicos: number } }

export default function Anomalias() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/anomalias");
  return (
    <div>
      <PageHeader title="Anomalías" subtitle="Detección automática de cuentas sin homologar y diferencias atípicas (z-score)" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Kpi label="Cuentas sin homologar" value={data.kpis.sin_homologar} tone="amber" hint="con movimiento PYG" />
              <Kpi label="Grupos atípicos" value={data.kpis.grupos_atipicos} tone="red" hint="z-score ≥ 2" />
              <Kpi label="Periodos analizados" value={data.periodos.length} hint={data.nota_zscore} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <Card title="Grupos con diferencia atípica (z-score)">
                {data.grupos_atipicos.length === 0 ? (
                  <p className="text-sm text-slate-400">Ningún grupo se desvía significativamente (z &lt; 2).</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase text-slate-400"><tr><th className="text-left py-2">Grupo</th><th className="text-left">Tipo</th><th className="text-right">Diferencia</th><th className="text-right">z</th></tr></thead>
                    <tbody>{data.grupos_atipicos.map((g, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-1.5 max-w-[200px] truncate" title={g.grupo}>{g.grupo}</td>
                        <td className="capitalize">{g.tipo}</td>
                        <td className="text-right tabular-nums text-red-600">{fmtCOP(g.diferencia)}</td>
                        <td className="text-right tabular-nums font-semibold">{g.z}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                )}
              </Card>
              <Card title="Cuentas con movimiento sin homologar">
                {data.sin_homologar.length === 0 ? (
                  <p className="text-sm text-emerald-600">Todas las cuentas PYG con movimiento están homologadas. ✓</p>
                ) : (
                  <div className="overflow-auto max-h-[55vh]">
                    <table className="w-full text-sm">
                      <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-2">País</th><th className="text-left">Cuenta</th><th className="text-left">Nombre</th><th className="text-right">Valor</th></tr></thead>
                      <tbody>{data.sin_homologar.map((c, i) => (
                        <tr key={i} className="border-t border-slate-100">
                          <td className="py-1.5">{c.pais}</td>
                          <td className="font-mono text-xs">{c.codigo}</td>
                          <td className="max-w-[200px] truncate" title={c.nombre}>{c.nombre || "—"}</td>
                          <td className="text-right tabular-nums">{fmtCOP(c.valor)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              </Card>
            </div>
            <p className="text-xs text-slate-400 mt-3">
              Nota: con menos de 3 periodos, el z-score se calcula de forma transversal sobre los grupos. Al cargar más meses, se habilita el z-score temporal por cuenta automáticamente.
            </p>
          </>
        )}
      </DataState>
    </div>
  );
}
