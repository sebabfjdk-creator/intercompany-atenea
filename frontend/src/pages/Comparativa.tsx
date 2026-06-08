import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { fmtCOP, periodoLabel } from "../lib/format";
import { fmtFecha } from "../lib/daterange";
import { PageHeader, Kpi, Card, DataState, EstadoBadge, CausaBadge } from "../components/ui";

interface Celda { co: number; es: number; dif: number; pct: number; estado: string; causa: string | null }
interface Fila { grupo: string; tipo: string; celdas: Record<string, Celda>; total_co: number; total_es: number; total_dif: number }
interface Comp {
  periodos: string[]; filas: Fila[];
  kpis: { grupos: number; cruces: number; conciliados: number; excepciones: number; dif_total_abs: number };
}
interface CtaDet { cuenta: string; nombre: string; valores: Record<string, number> }
interface Detalle { colombia: CtaDet[]; espana: CtaDet[]; total_co: Record<string, number>; total_es: Record<string, number>; periodos: string[] }
interface MovTx { cuenta: string; periodo: string; fecha: string | null; concepto: string; debe: number; haber: number }

export default function Comparativa() {
  const { data, loading, error, reload } = useFetch<Comp>("/api/comparativa");
  const [exp, setExp] = useState<Set<string>>(new Set());
  const [cache, setCache] = useState<Record<string, Detalle>>({});
  const [cargando, setCargando] = useState<Set<string>>(new Set());
  // tercer nivel: movimientos por cuenta
  const [movExp, setMovExp] = useState<Set<string>>(new Set());
  const [movCache, setMovCache] = useState<Record<string, MovTx[] | "loading">>({});
  const nav = useNavigate();
  const empty = !!data && data.filas.length === 0;

  async function cargar(grupo: string) {
    if (cache[grupo]) return;
    setCargando((s) => new Set(s).add(grupo));
    try {
      const { data: det } = await api.get<Detalle>("/api/comparativa/detalle-grupo", { params: { grupo } });
      setCache((c) => ({ ...c, [grupo]: det }));
    } finally {
      setCargando((s) => { const n = new Set(s); n.delete(grupo); return n; });
    }
  }
  function toggle(grupo: string) {
    setExp((s) => { const n = new Set(s); if (n.has(grupo)) n.delete(grupo); else { n.add(grupo); cargar(grupo); } return n; });
  }
  function expandirTodos() {
    if (!data) return;
    setExp(new Set(data.filas.map((f) => f.grupo)));
    data.filas.forEach((f) => cargar(f.grupo));
  }
  async function toggleMov(pais: "CO" | "ES", cuenta: string) {
    const key = `${pais}:${cuenta}`;
    const abrir = !movExp.has(key);
    setMovExp((s) => { const n = new Set(s); abrir ? n.add(key) : n.delete(key); return n; });
    if (abrir && !movCache[key]) {
      setMovCache((c) => ({ ...c, [key]: "loading" }));
      try {
        const { data: r } = await api.get("/api/comparativa/movimientos-cuenta", { params: { pais, cuenta } });
        setMovCache((c) => ({ ...c, [key]: r.items as MovTx[] }));
      } catch { setMovCache((c) => ({ ...c, [key]: [] })); }
    }
  }

  const nCols = data ? 2 + data.periodos.length * 3 : 0;

  function SubTabla({ titulo, rows, totales, periodos, lado }: { titulo: string; rows: CtaDet[]; totales: Record<string, number>; periodos: string[]; lado: "co" | "es" }) {
    const pais = lado === "co" ? "CO" : "ES";
    const subCols = 3 + periodos.length;
    return (
      <div className="mb-2">
        <div className={`text-[11px] font-semibold uppercase mb-1 ${lado === "co" ? "text-co" : "text-es"}`}>{titulo}</div>
        <table className="w-full text-xs">
          <thead className="text-slate-400">
            <tr><th className="w-6"></th><th className="text-left px-2 py-0.5 w-28">Cuenta</th><th className="text-left">Descripción</th>{periodos.map((p) => <th key={p} className="text-right px-2">{periodoLabel(p)}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const key = `${pais}:${r.cuenta}`;
              const abierto = movExp.has(key);
              const movs = movCache[key];
              return (
                <Fragment key={r.cuenta + i}>
                  <tr className="hover:bg-white/60">
                    <td className="text-center">
                      <button onClick={() => toggleMov(pais, r.cuenta)} className="w-4 h-4 rounded border text-[10px] text-slate-500 hover:bg-slate-100" title="Ver movimientos">{abierto ? "−" : "+"}</button>
                    </td>
                    <td className="px-2 py-0.5 font-mono">{r.cuenta}</td>
                    <td className="max-w-[200px] truncate" title={r.nombre}>{r.nombre || "—"}</td>
                    {periodos.map((p) => <td key={p} className="text-right px-2 tabular-nums">{fmtCOP(r.valores[p] ?? 0)}</td>)}
                  </tr>
                  {abierto && (
                    <tr>
                      <td></td>
                      <td colSpan={subCols - 1} className="px-2 pb-2">
                        {movs === "loading" ? <div className="text-slate-400 text-[11px] py-1">Cargando movimientos…</div>
                          : movs && movs.length ? (
                            <table className="w-full text-[11px] bg-white rounded border border-slate-100">
                              <thead className="text-slate-400"><tr><th className="text-left px-2 py-0.5">Fecha</th><th className="text-left">Periodo</th><th className="text-left">Concepto</th><th className="text-right">Débito</th><th className="text-right px-2">Crédito</th></tr></thead>
                              <tbody>
                                {movs.map((m, j) => (
                                  <tr key={j} className="border-t border-slate-50">
                                    <td className="px-2 py-0.5 whitespace-nowrap">{fmtFecha(m.fecha)}</td>
                                    <td>{periodoLabel(m.periodo)}</td>
                                    <td className="max-w-[260px] truncate" title={m.concepto}>{m.concepto}</td>
                                    <td className="text-right tabular-nums">{m.debe ? fmtCOP(m.debe) : ""}</td>
                                    <td className="text-right tabular-nums px-2">{m.haber ? fmtCOP(m.haber) : ""}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : <div className="text-slate-300 text-[11px] py-1">Sin movimientos individuales para esta cuenta.</div>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={subCols} className="text-slate-300 px-2 py-1">Sin cuentas en este lado</td></tr>}
            <tr className="font-semibold border-t border-slate-200">
              <td></td><td className="px-2 py-0.5">Total</td><td></td>
              {periodos.map((p) => <td key={p} className="text-right px-2 tabular-nums">{fmtCOP(totales[p] ?? 0)}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Comparativa PYG" subtitle="Grupo → Cuenta → Transacción · trazabilidad de la diferencia hasta el asiento"
        action={data && !empty ? (
          <div className="flex gap-2">
            <button onClick={expandirTodos} className="px-3 py-1.5 text-sm border rounded text-slate-600">Expandir todos</button>
            <button onClick={() => setExp(new Set())} className="px-3 py-1.5 text-sm border rounded text-slate-600">Contraer todos</button>
            <button onClick={() => descargarArchivo("/api/comparativa/export", "comparativa.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">⬇️ Excel</button>
          </div>
        ) : null} />
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
                      <th className="text-left px-3 py-2">Grupo</th>
                      {data.periodos.map((p) => <th key={p} className="text-right px-3 py-2" colSpan={3}>{periodoLabel(p)}</th>)}
                    </tr>
                    <tr className="text-[10px]">
                      <th></th>
                      {data.periodos.flatMap((p) => [
                        <th key={p + "co"} className="text-right px-3 py-1 text-co">CO</th>,
                        <th key={p + "es"} className="text-right px-3 py-1 text-es">ES</th>,
                        <th key={p + "d"} className="text-right px-3 py-1">Dif</th>,
                      ])}
                    </tr>
                  </thead>
                  <tbody>
                    {data.filas.map((f, i) => (
                      <FilaGrupo key={f.grupo + i} f={f} periodos={data.periodos} abierto={exp.has(f.grupo)}
                        cargando={cargando.has(f.grupo)} det={cache[f.grupo]} nCols={nCols}
                        onToggle={() => toggle(f.grupo)} SubTabla={SubTabla} onCuenta={() => nav("/excepciones")} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <p className="text-xs text-slate-400 mt-3">CO = Colombia (Siesa) · ES = España (DELSOL). Expande un grupo → sus cuentas; expande una cuenta (+) → sus transacciones.</p>
          </>
        )}
      </DataState>
    </div>
  );
}

function FilaGrupo({ f, periodos, abierto, cargando, det, nCols, onToggle, SubTabla }: any) {
  return (
    <>
      <tr className="border-t border-slate-100 hover:bg-slate-50">
        <td className="px-3 py-2">
          <button onClick={onToggle} className="mr-2 w-5 h-5 rounded border text-xs text-slate-500 hover:bg-slate-100">{abierto ? "−" : "+"}</button>
          <span className="font-medium text-slate-700">{f.grupo}</span>
          <span className="ml-2 text-[10px] text-slate-400 uppercase">{f.tipo}</span>
        </td>
        {periodos.map((p: string) => {
          const c = f.celdas[p];
          if (!c) return <td key={p} colSpan={3} className="text-center text-slate-300">—</td>;
          return [
            <td key={p + "co"} className="text-right px-3 py-2 tabular-nums">{fmtCOP(c.co)}</td>,
            <td key={p + "es"} className="text-right px-3 py-2 tabular-nums">{fmtCOP(c.es)}</td>,
            <td key={p + "d"} className={`text-right px-3 py-2 tabular-nums ${c.estado === "conciliado" ? "text-emerald-600" : "text-red-600 font-medium"}`}>
              <div className="flex items-center justify-end gap-1">{fmtCOP(c.dif)}<EstadoBadge estado={c.estado} /></div>
              {c.causa && <div className="text-right"><CausaBadge causa={c.causa} /></div>}
            </td>,
          ];
        })}
      </tr>
      {abierto && (
        <tr className="bg-slate-50/70">
          <td colSpan={nCols} className="px-6 py-3">
            {cargando && !det ? <div className="text-slate-400 text-xs">Cargando detalle…</div> : det ? (
              <div className="border-l-2 border-slate-200 pl-3">
                <SubTabla titulo="Colombia" rows={det.colombia} totales={det.total_co} periodos={periodos} lado="co" />
                <SubTabla titulo="España" rows={det.espana} totales={det.total_es} periodos={periodos} lado="es" />
              </div>
            ) : <div className="text-slate-400 text-xs">Sin detalle.</div>}
          </td>
        </tr>
      )}
    </>
  );
}
