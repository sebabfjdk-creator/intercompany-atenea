import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Grupo { grupo: string; tipo: string; diferencia: number; z: number }
interface Cuenta { pais: string; codigo: string; nombre: string; valor: number }
interface Conflicto { codigo: string; grupos: string[] }
interface Multiples { colombia: Conflicto[]; espana: Conflicto[]; total: number }
interface Resp { sin_homologar: Cuenta[]; grupos_atipicos: Grupo[]; multiples_grupos: Multiples; periodos: string[]; nota_zscore: string; kpis: { sin_homologar: number; grupos_atipicos: number; multiples_grupos: number } }

export default function Anomalias() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/anomalias");
  return (
    <div>
      <PageHeader title="Anomalías" subtitle="Detección automática de cuentas sin homologar y diferencias atípicas (z-score)" />
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <Kpi label="Cuentas sin homologar" value={data.kpis.sin_homologar} tone="amber" hint="con movimiento PYG" />
              <Kpi label="Grupos atípicos" value={data.kpis.grupos_atipicos} tone="red" hint="z-score ≥ 2" />
              <Kpi label="Cuentas en >1 grupo" value={data.kpis.multiples_grupos} tone="red" hint="doble conteo" />
              <Kpi label="Periodos analizados" value={data.periodos.length} hint={data.nota_zscore} />
            </div>

            {data.multiples_grupos.total > 0 && (
              <Card title="⚠️ Cuentas homologadas en más de un grupo (doble conteo)" className="mb-4">
                <p className="text-xs text-slate-500 mb-3">
                  Cada cuenta debe pertenecer a <b>un solo grupo</b>. Estas aparecen en varios (por código exacto
                  o porque un <b>wildcard</b> de un grupo cubre cuentas de otro), inflando los totales de Comparativa.
                </p>
                <div className="grid md:grid-cols-2 gap-4">
                  {(["espana", "colombia"] as const).map((lado) => (
                    <div key={lado}>
                      <div className={`text-xs font-semibold uppercase mb-1 ${lado === "espana" ? "text-es" : "text-co"}`}>
                        {lado === "espana" ? "España" : "Colombia"} ({data.multiples_grupos[lado].length})
                      </div>
                      {data.multiples_grupos[lado].length === 0 ? (
                        <p className="text-sm text-emerald-600">Sin conflictos. ✓</p>
                      ) : (
                        <div className="overflow-auto max-h-[40vh]">
                          <table className="w-full text-sm">
                            <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-1">Cuenta</th><th className="text-left">Grupos</th></tr></thead>
                            <tbody>{data.multiples_grupos[lado].map((c, i) => (
                              <tr key={i} className="border-t border-slate-100 align-top">
                                <td className="py-1.5 font-mono text-xs whitespace-nowrap">{c.codigo}</td>
                                <td className="text-xs">{c.grupos.join(" · ")}</td>
                              </tr>
                            ))}</tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}
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
