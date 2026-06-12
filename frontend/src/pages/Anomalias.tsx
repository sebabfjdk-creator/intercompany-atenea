import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Grupo { grupo: string; tipo: string; diferencia: number; z: number }
interface Cuenta { pais: string; codigo: string; nombre: string; valor: number }
interface Conflicto { codigo: string; grupos: string[] }
interface Multiples { colombia: Conflicto[]; espana: Conflicto[]; total: number }
interface CobItem { pais: string; codigo: string; nombre: string; valor: number; grupos?: string[] }
interface Cobertura { huecos: CobItem[]; dobles: CobItem[]; kpis: { huecos: number; dobles: number; monto_huecos: number; monto_dobles: number } }
interface Resp { sin_homologar: Cuenta[]; grupos_atipicos: Grupo[]; multiples_grupos: Multiples; cobertura: Cobertura; periodos: string[]; nota_zscore: string; kpis: { sin_homologar: number; grupos_atipicos: number; multiples_grupos: number; huecos: number; dobles: number } }

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

            {data.cobertura && (data.cobertura.kpis.huecos > 0 || data.cobertura.kpis.dobles > 0) && (
              <Card title="🔎 Validación de cobertura PYG (consciente de jerarquía)" className="mb-4">
                <p className="text-xs text-slate-500 mb-3">
                  Sobre las <b>cuentas hoja</b> (movimiento real) de clases 4/5 (CO) y 6/7 (ES). Cada hoja debe estar
                  cubierta por <b>un solo</b> código homologado. <b>Hueco</b> = no entra a Comparativa; <b>doble conteo</b> =
                  cubierta por padre e hijo, o por wildcard que pisa.
                </p>
                <div className="grid grid-cols-2 md:grid-cols-2 gap-4 mb-3">
                  <Kpi label="Huecos (sin contar)" value={data.cobertura.kpis.huecos} tone="amber" hint={fmtCOP(data.cobertura.kpis.monto_huecos)} />
                  <Kpi label="Dobles conteos" value={data.cobertura.kpis.dobles} tone="red" hint={fmtCOP(data.cobertura.kpis.monto_dobles)} />
                </div>
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs font-semibold uppercase text-amber-600 mb-1">Huecos — movimiento sin homologar</div>
                    {data.cobertura.huecos.length === 0 ? <p className="text-sm text-emerald-600">Sin huecos. ✓</p> : (
                      <div className="overflow-auto max-h-[40vh]">
                        <table className="w-full text-sm">
                          <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-1">País</th><th className="text-left">Cuenta</th><th className="text-left">Nombre</th><th className="text-right">Valor</th></tr></thead>
                          <tbody>{data.cobertura.huecos.map((c, i) => (
                            <tr key={i} className="border-t border-slate-100">
                              <td className="py-1">{c.pais}</td><td className="font-mono text-xs">{c.codigo}</td>
                              <td className="max-w-[160px] truncate" title={c.nombre}>{c.nombre || "—"}</td>
                              <td className="text-right tabular-nums">{fmtCOP(c.valor)}</td>
                            </tr>
                          ))}</tbody>
                        </table>
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="text-xs font-semibold uppercase text-red-600 mb-1">Dobles conteos</div>
                    {data.cobertura.dobles.length === 0 ? <p className="text-sm text-emerald-600">Sin dobles conteos. ✓</p> : (
                      <div className="overflow-auto max-h-[40vh]">
                        <table className="w-full text-sm">
                          <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-1">Cuenta</th><th className="text-right">Valor</th><th className="text-left">Cubierta por</th></tr></thead>
                          <tbody>{data.cobertura.dobles.map((c, i) => (
                            <tr key={i} className="border-t border-slate-100 align-top">
                              <td className="py-1 font-mono text-xs whitespace-nowrap">{c.pais} {c.codigo}</td>
                              <td className="text-right tabular-nums">{fmtCOP(c.valor)}</td>
                              <td className="text-xs">{(c.grupos ?? []).join(" · ")}</td>
                            </tr>
                          ))}</tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            )}

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
