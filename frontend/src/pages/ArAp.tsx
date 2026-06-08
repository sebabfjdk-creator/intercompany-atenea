import { useMemo, useState } from "react";
import { descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { fmtFecha } from "../lib/daterange";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Fila { tipo: string; categoria: string; nit: string; nombre: string; saldo_co: number; saldo_es: number; diferencia: number; estado: string; error_contab: boolean; matched_por?: string | null }
interface TotCat { debitos: number; creditos: number; saldo_neto: number }
interface Comp { filas: Fila[]; totales: Record<string, TotCat> }

function EstadoBadge({ estado }: { estado: string }) {
  const map: Record<string, string> = {
    CONCILIADO: "bg-emerald-100 text-emerald-700", DIFERENCIA: "bg-red-100 text-red-700",
    ERROR_CO: "bg-purple-100 text-purple-700", SIN_MATCH: "bg-slate-200 text-slate-600",
    Conciliado: "bg-emerald-100 text-emerald-700", "Diferencia temporal": "bg-amber-100 text-amber-700",
    "Diferencia permanente": "bg-red-100 text-red-700", "Pendiente de revisión": "bg-purple-100 text-purple-700",
  };
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[estado] ?? "bg-slate-100"}`}>{estado}</span>;
}
const CatBadge = ({ cat }: { cat: string }) => (
  <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${cat === "CLIENTE" ? "bg-blue-100 text-blue-700" : "bg-orange-100 text-orange-700"}`}>{cat}</span>
);
const signo = (n: number) => (n < 0 ? "text-red-600" : "text-emerald-600");

const TABS = ["Conciliación", "Indicadores", "Errores contables", "Provisionales (ES)"] as const;

export default function ArAp() {
  const [tab, setTab] = useState(0);
  const [selNit, setSelNit] = useState<string | null>(null);
  function verTercero(nit: string) { setSelNit(nit); setTab(0); }
  return (
    <div>
      <PageHeader title="AR/AP — Trazabilidad por tercero" subtitle="Del saldo al asiento: documento, tipo, línea de tiempo y matching CO↔ES"
        action={<button onClick={() => descargarArchivo("/api/ar-ap/export", "ar-ap.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">⬇️ Excel</button>} />
      <div className="flex gap-2 mb-4 border-b border-slate-200">
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)} className={`px-4 py-2 text-sm -mb-px border-b-2 ${tab === i ? "border-co text-co font-medium" : "border-transparent text-slate-500"}`}>{t}</button>
        ))}
      </div>
      {tab === 0 && <Conciliacion sel={selNit} setSel={setSelNit} />}
      {tab === 1 && <Indicadores onVer={verTercero} />}
      {tab === 2 && <Errores />}
      {tab === 3 && <Provisionales />}
    </div>
  );
}

function SplitPane({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  const [w] = useState<number>(() => Number(localStorage.getItem("arap_split") ?? 540));
  const mobile = window.innerWidth < 768;
  if (mobile) return <div className="space-y-4">{left}{right}</div>;
  return (
    <div className="flex items-stretch gap-3" style={{ height: "calc(100vh - 230px)" }}>
      <div style={{ width: w }} className="overflow-auto">{left}</div>
      <div className="flex-1 overflow-auto">{right}</div>
    </div>
  );
}

function Conciliacion({ sel, setSel }: { sel: string | null; setSel: (n: string | null) => void }) {
  const { data, loading, error, reload } = useFetch<Comp>("/api/ar-ap/comparativa");
  const [tipo, setTipo] = useState(""); const [estado, setEstado] = useState("");
  const empty = !!data && data.filas.length === 0;
  const filas = useMemo(() => (data?.filas ?? []).filter((f) => (!tipo || f.tipo === tipo) && (!estado || f.estado === estado)), [data, tipo, estado]);

  const left = (
    <Card className="h-full">
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="flex gap-2 mb-3">
              <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="border rounded px-2 py-1 text-sm"><option value="">AR+AP</option><option value="AR">Cobrar</option><option value="AP">Pagar</option></select>
              <select value={estado} onChange={(e) => setEstado(e.target.value)} className="border rounded px-2 py-1 text-sm"><option value="">Estados</option>{["CONCILIADO","DIFERENCIA","ERROR_CO","SIN_MATCH"].map(s=><option key={s}>{s}</option>)}</select>
              <span className="ml-auto self-center text-xs text-slate-400">{filas.length}</span>
            </div>
            <div className="overflow-auto max-h-[58vh]">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-2">Tercero</th><th>Cat</th><th className="text-right">CO</th><th className="text-right">ES</th><th className="text-right">Dif</th><th></th></tr></thead>
                <tbody>
                  {filas.map((f, i) => (
                    <tr key={f.nit + f.tipo + i} className={`border-t border-slate-100 hover:bg-slate-50 ${sel === f.nit ? "bg-blue-50" : ""}`}>
                      <td className="py-1.5 max-w-[150px] truncate" title={f.nombre}>
                        {f.nombre || "—"}
                        {f.matched_por === "nombre" && <span className="ml-1 text-[9px] px-1 rounded bg-indigo-100 text-indigo-700" title="Cruzado por nombre (sin NIT común)">↔ nombre</span>}
                      </td>
                      <td><CatBadge cat={f.categoria} /></td>
                      <td className="text-right tabular-nums">{fmtCOP(f.saldo_co)}</td>
                      <td className="text-right tabular-nums">{fmtCOP(f.saldo_es)}</td>
                      <td className={`text-right tabular-nums ${signo(f.diferencia)}`}>{fmtCOP(f.diferencia)}</td>
                      <td>{f.nit && <button onClick={() => setSel(f.nit)} className="text-co text-xs hover:underline">Ver →</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </DataState>
    </Card>
  );
  return <SplitPane left={left} right={<Tercero360 nit={sel} />} />;
}

function Tercero360({ nit }: { nit: string | null }) {
  const [filtroDoc, setFiltroDoc] = useState("");
  const { data, loading, error } = useFetch<any>(nit ? `/api/ar-ap/tercero/${nit}` : null);
  if (!nit) return <Card className="h-full"><div className="text-slate-400 text-sm py-16 text-center">Selecciona un tercero y pulsa <b>"Ver →"</b> para la trazabilidad completa.</div></Card>;
  if (loading) return <Card><div className="py-16 text-center text-slate-400">Cargando…</div></Card>;
  if (error || !data) return <Card><div className="py-16 text-center text-red-600">{error ?? "Error"}</div></Card>;
  const r = data.resumen;
  const filtra = (rows: any[]) => filtroDoc ? rows.filter((m) => (m.tipo_documento || "") === filtroDoc) : rows;
  const tiposDoc = [...new Set([...data.movimientos_co, ...data.movimientos_es].map((m: any) => m.tipo_documento).filter(Boolean))] as string[];

  return (
    <div className="space-y-3">
      <Card>
        <div className="flex items-start justify-between">
          <div><div className="font-bold text-lg text-slate-800">{data.nombre || "—"}</div><div className="text-xs font-mono text-slate-500">NIT/NIF: {data.nit}</div></div>
          <EstadoBadge estado={r.estado} />
        </div>
        <div className="grid grid-cols-3 gap-3 mt-3 text-sm">
          <div><div className="text-[10px] uppercase text-slate-400">Saldo CO</div><div className="font-semibold tabular-nums">{fmtCOP(r.saldo_co)}</div></div>
          <div><div className="text-[10px] uppercase text-slate-400">Saldo ES</div><div className="font-semibold tabular-nums">{fmtCOP(r.saldo_es)}</div></div>
          <div><div className="text-[10px] uppercase text-slate-400">Diferencia</div><div className={`font-bold tabular-nums ${signo(r.diferencia)}`}>{fmtCOP(r.diferencia)}</div></div>
          <div><div className="text-[10px] uppercase text-slate-400">Antigüedad</div><div>{r.antiguedad}</div></div>
          <div><div className="text-[10px] uppercase text-slate-400">Mes origen</div><div>{r.mes_origen ?? "—"}</div></div>
          <div><div className="text-[10px] uppercase text-slate-400">Último mov.</div><div>{fmtFecha(r.ultimo_movimiento)}</div></div>
        </div>
      </Card>

      {data.analisis?.length > 0 && (
        <Card title="Análisis automático de la diferencia">
          <ul className="text-sm space-y-1 list-disc pl-5">{data.analisis.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>
        </Card>
      )}

      {data.matching?.length > 0 && (
        <Card title="Matching documental CO ↔ ES">
          <table className="w-full text-xs">
            <thead className="text-slate-400"><tr><th className="text-left py-1">Doc Colombia</th><th className="text-right">Valor</th><th></th><th className="text-left">Doc España</th><th className="text-right">Valor</th><th className="text-right">Confianza</th></tr></thead>
            <tbody>{data.matching.map((m: any, i: number) => (
              <tr key={i} className="border-t border-slate-50">
                <td className="py-1 font-mono">{m.co_documento}</td><td className="text-right tabular-nums">{fmtCOP(m.co_valor)}</td>
                <td className="text-center text-slate-400">↔</td>
                <td className="font-mono">{m.es_documento}</td><td className="text-right tabular-nums">{fmtCOP(m.es_valor)}</td>
                <td className="text-right"><span className={`px-2 py-0.5 rounded-full text-[10px] ${m.confianza >= 95 ? "bg-emerald-100 text-emerald-700" : m.confianza >= 80 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}>{m.confianza}%</span></td>
              </tr>
            ))}</tbody>
          </table>
        </Card>
      )}

      <Card title="Línea de tiempo financiera">
        {tiposDoc.length > 0 && (
          <select value={filtroDoc} onChange={(e) => setFiltroDoc(e.target.value)} className="border rounded px-2 py-1 text-xs mb-2"><option value="">Todos los tipos</option>{tiposDoc.map((t) => <option key={t}>{t}</option>)}</select>
        )}
        <div className="space-y-1 max-h-48 overflow-auto">
          {data.timeline.map((t: any, i: number) => (
            <div key={i} className="flex items-center gap-2 text-xs border-l-2 pl-2 py-0.5" style={{ borderColor: t.pais === "CO" ? "#1565c0" : "#c62828" }}>
              <span className="w-20 text-slate-500">{fmtFecha(t.fecha)}</span>
              <span className="flex-1">{t.evento} <span className="font-mono text-slate-400">{t.documento}</span></span>
              <span className={`tabular-nums ${signo(t.valor)}`}>{fmtCOP(t.valor)}</span>
            </div>
          ))}
          {data.timeline.length === 0 && <div className="text-slate-300 text-xs">Sin movimientos con fecha.</div>}
        </div>
      </Card>

      <MovTabla titulo="Movimientos Colombia (1305/2805/22xx)" rows={filtra(data.movimientos_co)} />
      <MovTabla titulo="Movimientos España (430/410)" rows={filtra(data.movimientos_es)} />
    </div>
  );
}

function MovTabla({ titulo, rows }: { titulo: string; rows: any[] }) {
  return (
    <Card title={`${titulo} (${rows.length})`}>
      <div className="overflow-auto max-h-60">
        <table className="w-full text-[11px]">
          <thead className="text-slate-400 sticky top-0 bg-white"><tr>
            <th className="text-left px-1 py-0.5">Fecha</th><th className="text-left">Periodo</th><th className="text-left">Cuenta</th><th className="text-left">Documento</th><th className="text-left">Tipo</th><th className="text-left">Concepto</th><th className="text-right">Débito</th><th className="text-right">Crédito</th><th className="text-right px-1">Saldo</th></tr></thead>
          <tbody>
            {rows.map((m, i) => (
              <tr key={i} className="border-t border-slate-50">
                <td className="px-1 py-0.5 whitespace-nowrap">{fmtFecha(m.fecha)}</td><td>{m.periodo}</td>
                <td className="font-mono">{m.cuenta}</td><td className="font-mono">{m.documento}</td><td>{m.tipo_documento}</td>
                <td className="max-w-[160px] truncate" title={m.concepto}>{m.concepto}</td>
                <td className="text-right tabular-nums">{m.debe ? fmtCOP(m.debe) : ""}</td>
                <td className="text-right tabular-nums">{m.haber ? fmtCOP(m.haber) : ""}</td>
                <td className="text-right tabular-nums px-1">{fmtCOP(m.saldo)}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={9} className="text-slate-300 px-2 py-2 text-center">Sin movimientos</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Indicadores({ onVer }: { onVer: (nit: string) => void }) {
  const { data, loading, error, reload } = useFetch<any>("/api/ar-ap/kpis");
  return (
    <DataState loading={loading} error={error} onRetry={reload}>
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Kpi label="Diferencias abiertas" value={data.diferencias_abiertas} tone="red" />
            <Kpi label="Conciliadas" value={data.diferencias_conciliadas} tone="green" />
            <Kpi label="> 90 días" value={data.mayores_90_dias} tone="amber" />
            <Kpi label="Monto abierto" value={fmtCOP(data.monto_abierto)} tone="blue" />
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <Card title="Top 20 terceros con mayor diferencia">
              <div className="overflow-auto max-h-[55vh]">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-2">Tercero</th><th className="text-right">Diferencia</th><th>Estado</th><th>Días</th><th></th></tr></thead>
                  <tbody>{data.top_terceros.map((t: any, i: number) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-1.5 max-w-[200px] truncate" title={t.nombre}>{t.nombre || t.nit}</td>
                      <td className={`text-right tabular-nums ${signo(t.diferencia)}`}>{fmtCOP(t.diferencia)}</td>
                      <td className="text-center"><EstadoBadge estado={t.estado} /></td>
                      <td className="text-center text-xs text-slate-500">{t.dias ?? "—"}</td>
                      <td>{t.nit && <button onClick={() => onVer(t.nit)} className="text-co text-xs hover:underline">Ver →</button>}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </Card>
            <Card title="Top cuentas con mayor diferencia">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400"><tr><th className="text-left py-2">Cuenta</th><th className="text-right">Monto</th></tr></thead>
                <tbody>{data.top_cuentas.map((c: any, i: number) => (
                  <tr key={i} className="border-t border-slate-100"><td className="py-1.5 font-mono text-xs">{c.cuenta}</td><td className="text-right tabular-nums">{fmtCOP(c.monto)}</td></tr>
                ))}</tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </DataState>
  );
}

function Errores() {
  const { data, loading, error, reload } = useFetch<any[]>("/api/ar-ap/errores");
  const empty = !!data && data.length === 0;
  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      <Card>
        <p className="text-sm text-amber-700 bg-amber-50 rounded p-3 mb-4">Posible error de contabilización: saldo negativo en cuenta 1305. Verificar reclasificación a 2805.</p>
        <table className="w-full text-sm"><thead className="text-xs uppercase text-slate-400"><tr><th className="text-left py-2">NIT</th><th className="text-left">Nombre</th><th className="text-right">1305</th><th className="text-right">2805</th></tr></thead>
          <tbody>{(data ?? []).map((e: any, i: number) => (<tr key={i} className="border-t border-slate-100"><td className="py-2 font-mono text-xs">{e.nit}</td><td>{e.nombre}</td><td className="text-right tabular-nums text-red-600">{fmtCOP(e.saldo_1305)}</td><td className="text-right tabular-nums">{fmtCOP(e.saldo_2805)}</td></tr>))}</tbody>
        </table>
      </Card>
    </DataState>
  );
}
function Provisionales() {
  const { data, loading, error, reload } = useFetch<any[]>("/api/ar-ap/cuentas-amarillas");
  const empty = !!data && data.length === 0;
  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      <Card>
        <p className="text-sm text-orange-700 bg-orange-50 rounded p-3 mb-4">Cuentas provisionales (amarillas) pendientes de facturación: <b>no cruzan</b> con Colombia.</p>
        <table className="w-full text-sm"><thead className="text-xs uppercase text-slate-400"><tr><th className="text-left py-2">Cuenta ES</th><th className="text-left">Nombre</th><th className="text-left">Tipo</th><th className="text-right">Saldo</th></tr></thead>
          <tbody>{(data ?? []).map((p: any, i: number) => (<tr key={i} className="border-t border-slate-100"><td className="py-2 font-mono text-xs">{p.cuenta_es}</td><td>{p.nombre}</td><td>{p.tipo}</td><td className="text-right tabular-nums">{fmtCOP(p.saldo)}</td></tr>))}</tbody>
        </table>
      </Card>
    </DataState>
  );
}
