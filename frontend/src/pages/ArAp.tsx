import { useEffect, useMemo, useRef, useState } from "react";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { rangoChip, fmtFecha } from "../lib/daterange";
import { PageHeader, Card, DataState } from "../components/ui";

interface Fila {
  tipo: string; categoria: string; nit: string; nombre: string;
  saldo_co: number; saldo_es: number; saldo_1305: number | null; saldo_2805: number | null;
  debitos_mes: number; creditos_mes: number; diferencia: number; estado: string; error_contab: boolean;
}
interface TotCat { debitos: number; creditos: number; saldo_neto: number }
interface Comp { filas: Fila[]; totales: Record<string, TotCat>; kpis: any }
interface Mov { fecha: string | null; cuenta: string; concepto: string; debe: number; haber: number; saldo: number }
interface Detalle {
  nit: string; nombre: string; movimientos_co: Mov[]; movimientos_es: Mov[];
  resumen: { saldo_1305: number; saldo_2805: number; saldo_co: number; saldo_es: number; diferencia: number };
  alertas: { tipo: string; msg: string }[];
}

function ArApBadge({ estado }: { estado: string }) {
  const map: Record<string, string> = {
    CONCILIADO: "bg-emerald-100 text-emerald-700", DIFERENCIA: "bg-red-100 text-red-700",
    ERROR_CO: "bg-purple-100 text-purple-700", SIN_MATCH: "bg-slate-200 text-slate-600",
  };
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[estado] ?? "bg-slate-100"}`}>{estado}</span>;
}
function CatBadge({ cat }: { cat: string }) {
  const cli = cat === "CLIENTE";
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${cli ? "bg-blue-100 text-blue-700" : "bg-orange-100 text-orange-700"}`}>{cat}</span>;
}
const signo = (n: number) => (n < 0 ? "text-red-600" : "text-emerald-600");

const TABS = ["Conciliación", "Errores contables", "Provisionales (ES)"] as const;

export default function ArAp() {
  const [tab, setTab] = useState(0);
  return (
    <div>
      <PageHeader title="AR/AP — Cuentas por Cobrar y Pagar" subtitle="Conciliación de saldos por tercero (NIT ↔ NIF)" />
      <div className="flex gap-2 mb-4 border-b border-slate-200">
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            className={`px-4 py-2 text-sm -mb-px border-b-2 ${tab === i ? "border-co text-co font-medium" : "border-transparent text-slate-500"}`}>{t}</button>
        ))}
      </div>
      {tab === 0 && <Conciliacion />}
      {tab === 1 && <Errores />}
      {tab === 2 && <Provisionales />}
    </div>
  );
}

// ---------- Date range (persistido entre pestañas en localStorage) ----------
function DateRange({ desde, hasta, onChange }: { desde: string; hasta: string; onChange: (d: string, h: string) => void }) {
  const chips: [string, string][] = [["mes_actual", "Mes actual"], ["mes_anterior", "Mes anterior"], ["trimestre", "Trimestre"], ["anio", "Año"]];
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <label className="text-xs text-slate-500">Desde</label>
      <input type="date" value={desde} onChange={(e) => onChange(e.target.value, hasta)} className="border rounded px-2 py-1 text-sm" />
      <label className="text-xs text-slate-500">Hasta</label>
      <input type="date" value={hasta} onChange={(e) => onChange(desde, e.target.value)} className="border rounded px-2 py-1 text-sm" />
      {chips.map(([id, label]) => (
        <button key={id} onClick={() => { const r = rangoChip(id); onChange(r.desde, r.hasta); }}
          className="px-2 py-1 text-xs rounded bg-slate-100 hover:bg-slate-200">{label}</button>
      ))}
      <button onClick={() => onChange("", "")} className="px-2 py-1 text-xs rounded bg-slate-100 hover:bg-slate-200">Todo</button>
    </div>
  );
}

// ---------- Split pane redimensionable (zero-dep) ----------
function SplitPane({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  const [w, setW] = useState<number>(() => Number(localStorage.getItem("arap_split") ?? 560));
  const [mobile, setMobile] = useState(window.innerWidth < 768);
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef(false);

  useEffect(() => {
    const onResize = () => setMobile(window.innerWidth < 768);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!drag.current || !ref.current) return;
      const x = e.clientX - ref.current.getBoundingClientRect().left;
      setW(Math.max(250, Math.min(x, ref.current.clientWidth - 250)));
    };
    const up = () => { if (drag.current) { drag.current = false; localStorage.setItem("arap_split", String(w)); document.body.style.cursor = ""; } };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [w]);

  if (mobile) return <div className="space-y-4">{left}{right}</div>;
  return (
    <div ref={ref} className="flex items-stretch" style={{ height: "calc(100vh - 230px)" }}>
      <div style={{ width: w }} className="overflow-auto pr-1">{left}</div>
      <div onMouseDown={() => { drag.current = true; document.body.style.cursor = "col-resize"; }}
        className="w-1.5 mx-1 cursor-col-resize bg-slate-200 hover:bg-co rounded" title="Arrastra para redimensionar" />
      <div className="flex-1 overflow-auto pl-1">{right}</div>
    </div>
  );
}

// ---------- Pestaña Conciliación ----------
function Conciliacion() {
  const [desde, setDesde] = useState(() => localStorage.getItem("arap_desde") ?? "");
  const [hasta, setHasta] = useState(() => localStorage.getItem("arap_hasta") ?? "");
  const [sel, setSel] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<keyof Fila>("diferencia");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  function setRange(d: string, h: string) {
    setDesde(d); setHasta(h);
    localStorage.setItem("arap_desde", d); localStorage.setItem("arap_hasta", h);
  }
  const qs = `${desde ? `&desde=${desde}` : ""}${hasta ? `&hasta=${hasta}` : ""}`;
  const { data, loading, error, reload } = useFetch<Comp>(`/api/ar-ap/comparativa?${qs}`);
  const empty = !!data && data.filas.length === 0;

  const filas = useMemo(() => {
    const arr = [...(data?.filas ?? [])];
    arr.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    return arr;
  }, [data, sortKey, sortDir]);

  function th(label: string, key: keyof Fila, right = false) {
    return (
      <th onClick={() => { setSortKey(key); setSortDir(sortKey === key ? (sortDir === 1 ? -1 : 1) : -1); }}
        className={`px-2 py-2 cursor-pointer select-none ${right ? "text-right" : "text-left"}`}>
        {label}{sortKey === key ? (sortDir === 1 ? " ▲" : " ▼") : ""}
      </th>
    );
  }

  const left = (
    <Card className="h-full">
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                <tr>
                  {th("Tercero", "nombre")}{th("Cat.", "categoria")}
                  {th("Σ Déb", "debitos_mes", true)}{th("Σ Créd", "creditos_mes", true)}
                  {th("Saldo neto", "diferencia", true)}{th("Estado", "estado")}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f, i) => (
                  <tr key={f.nit + f.tipo + i} className={`border-t border-slate-100 hover:bg-slate-50 ${sel === f.nit ? "bg-blue-50" : ""}`}>
                    <td className="px-2 py-1.5 max-w-[180px] truncate" title={f.nombre}>{f.nombre || "—"}</td>
                    <td className="px-2"><CatBadge cat={f.categoria} /></td>
                    <td className="px-2 text-right tabular-nums">{fmtCOP(f.debitos_mes)}</td>
                    <td className="px-2 text-right tabular-nums">{fmtCOP(f.creditos_mes)}</td>
                    <td className={`px-2 text-right tabular-nums ${signo(f.diferencia)}`}>{fmtCOP(f.diferencia)}</td>
                    <td className="px-2"><ArApBadge estado={f.estado} /></td>
                    <td className="px-2">{f.nit && <button onClick={() => setSel(f.nit)} className="text-co text-xs hover:underline whitespace-nowrap">Ver más →</button>}</td>
                  </tr>
                ))}
              </tbody>
              {data.totales && (
                <tfoot className="sticky bottom-0 bg-white">
                  {(["CLIENTES", "PROVEEDORES", "TOTAL"] as const).map((k) => (
                    <tr key={k} className={`border-t ${k === "TOTAL" ? "border-slate-300 font-bold" : "border-slate-100 font-medium"}`}>
                      <td className="px-2 py-1.5" colSpan={2}>{k}</td>
                      <td className="px-2 text-right tabular-nums">{fmtCOP(data.totales[k].debitos)}</td>
                      <td className="px-2 text-right tabular-nums">{fmtCOP(data.totales[k].creditos)}</td>
                      <td className={`px-2 text-right tabular-nums ${signo(data.totales[k].saldo_neto)}`}>{fmtCOP(data.totales[k].saldo_neto)}</td>
                      <td colSpan={2}></td>
                    </tr>
                  ))}
                </tfoot>
              )}
            </table>
          </div>
        )}
      </DataState>
    </Card>
  );

  return (
    <>
      <DateRange desde={desde} hasta={hasta} onChange={setRange} />
      <SplitPane left={left} right={<Detalle nit={sel} desde={desde} hasta={hasta} />} />
    </>
  );
}

function MovTable({ titulo, movs }: { titulo: string; movs: Mov[] }) {
  return (
    <div className="mb-4">
      <div className="text-xs font-semibold text-slate-600 mb-1">{titulo} ({movs.length})</div>
      <div className="overflow-x-auto max-h-60 border border-slate-100 rounded">
        <table className="w-full text-xs">
          <thead className="text-slate-400 sticky top-0 bg-white"><tr>
            <th className="text-left px-2 py-1">Fecha</th><th className="text-left">Cuenta</th><th className="text-left">Concepto</th>
            <th className="text-right">Débito</th><th className="text-right">Crédito</th><th className="text-right px-2">Saldo</th></tr></thead>
          <tbody>
            {movs.map((m, i) => (
              <tr key={i} className="border-t border-slate-50">
                <td className="px-2 py-1 whitespace-nowrap">{fmtFecha(m.fecha)}</td>
                <td className="font-mono">{m.cuenta}</td>
                <td className="max-w-[180px] truncate" title={m.concepto}>{m.concepto}</td>
                <td className="text-right tabular-nums">{m.debe ? fmtCOP(m.debe) : ""}</td>
                <td className="text-right tabular-nums">{m.haber ? fmtCOP(m.haber) : ""}</td>
                <td className="text-right tabular-nums px-2">{fmtCOP(m.saldo)}</td>
              </tr>
            ))}
            {movs.length === 0 && <tr><td colSpan={6} className="text-center text-slate-300 py-3">Sin movimientos</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Detalle({ nit, desde, hasta }: { nit: string | null; desde: string; hasta: string }) {
  const qs = `${desde ? `&desde=${desde}` : ""}${hasta ? `&hasta=${hasta}` : ""}`;
  const { data, loading, error } = useFetch<Detalle>(nit ? `/api/ar-ap/movimientos-tercero?nit=${nit}${qs}` : null);
  if (!nit) return <Card className="h-full"><div className="text-slate-400 text-sm py-16 text-center">Selecciona un tercero y pulsa <b>“Ver más →”</b> para ver el detalle.</div></Card>;
  if (loading) return <Card><div className="py-16 text-center text-slate-400">Cargando…</div></Card>;
  if (error || !data) return <Card><div className="py-16 text-center text-red-600">{error ?? "Error"}</div></Card>;
  const r = data.resumen;
  const alertColor: Record<string, string> = { error: "bg-red-50 text-red-700", info: "bg-blue-50 text-blue-700", warn: "bg-amber-50 text-amber-700" };
  return (
    <Card className="h-full">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="font-bold text-slate-800">{data.nombre || "—"}</div>
          <div className="text-xs text-slate-500 font-mono">NIT/NIF: {data.nit}</div>
        </div>
      </div>
      {data.alertas.map((a, i) => (
        <div key={i} className={`text-xs rounded p-2 mb-2 ${alertColor[a.tipo] ?? "bg-slate-50"}`}>{a.msg}</div>
      ))}
      <MovTable titulo="Movimientos Colombia (1305 / 2805 / 22xx)" movs={data.movimientos_co} />
      <MovTable titulo="Movimientos España (430 / 410)" movs={data.movimientos_es} />
      <div className="bg-slate-50 rounded p-3 text-sm font-mono space-y-1">
        <div className="flex justify-between"><span>Saldo Colombia (1305)</span><span>{fmtCOP(r.saldo_1305)}</span></div>
        <div className="flex justify-between"><span>Saldo Colombia (2805)</span><span>{fmtCOP(r.saldo_2805)}</span></div>
        <div className="flex justify-between font-semibold border-t border-slate-200 pt-1"><span>Saldo neto Colombia</span><span>{fmtCOP(r.saldo_co)}</span></div>
        <div className="flex justify-between"><span>Saldo España (430/410)</span><span>{fmtCOP(r.saldo_es)}</span></div>
        <div className={`flex justify-between font-bold border-t border-slate-200 pt-1 ${Math.abs(r.diferencia) > 1000 ? "text-red-600" : "text-emerald-600"}`}><span>Diferencia</span><span>{fmtCOP(r.diferencia)}</span></div>
      </div>
    </Card>
  );
}

// ---------- Errores y Provisionales (sin cambios funcionales) ----------
function Errores() {
  const { data, loading, error, reload } = useFetch<{ nit: string; nombre: string; saldo_1305: number; saldo_2805: number }[]>("/api/ar-ap/errores");
  const empty = !!data && data.length === 0;
  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      <Card>
        <p className="text-sm text-amber-700 bg-amber-50 rounded p-3 mb-4">Posible error de contabilización: saldo negativo en cuenta 1305. Verificar si debe reclasificarse a 2805.</p>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-slate-400"><tr><th className="text-left py-2">NIT</th><th className="text-left">Nombre</th><th className="text-right">Saldo 1305</th><th className="text-right">Saldo 2805</th></tr></thead>
          <tbody>{(data ?? []).map((e, i) => (
            <tr key={e.nit + i} className="border-t border-slate-100"><td className="py-2 font-mono text-xs">{e.nit}</td><td>{e.nombre}</td>
              <td className="text-right tabular-nums text-red-600">{fmtCOP(e.saldo_1305)}</td><td className="text-right tabular-nums">{fmtCOP(e.saldo_2805)}</td></tr>
          ))}</tbody>
        </table>
      </Card>
    </DataState>
  );
}
function Provisionales() {
  const { data, loading, error, reload } = useFetch<{ cuenta_es: string; nombre: string; saldo: number; tipo: string }[]>("/api/ar-ap/cuentas-amarillas");
  const empty = !!data && data.length === 0;
  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      <Card>
        <p className="text-sm text-orange-700 bg-orange-50 rounded p-3 mb-4">Estas cuentas (amarillas en el Excel) están pendientes de facturación y <b>no cruzan</b> con Colombia.</p>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-slate-400"><tr><th className="text-left py-2">Cuenta ES</th><th className="text-left">Nombre</th><th className="text-left">Tipo</th><th className="text-right">Saldo</th></tr></thead>
          <tbody>{(data ?? []).map((p, i) => (
            <tr key={p.cuenta_es + i} className="border-t border-slate-100"><td className="py-2 font-mono text-xs">{p.cuenta_es} <span className="ml-1 px-2 py-0.5 rounded-full text-[10px] bg-orange-100 text-orange-700">PROVISIONAL</span></td>
              <td>{p.nombre}</td><td>{p.tipo}</td><td className="text-right tabular-nums">{fmtCOP(p.saldo)}</td></tr>
          ))}</tbody>
        </table>
      </Card>
    </DataState>
  );
}
