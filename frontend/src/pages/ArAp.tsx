import { useMemo, useState } from "react";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Fila {
  tipo: string; nit: string; nombre: string; saldo_co: number; saldo_es: number;
  saldo_1305: number | null; saldo_2805: number | null; diferencia: number; estado: string; error_contab: boolean;
}
interface Comp { filas: Fila[]; kpis: { terceros: number; conciliados: number; diferencias: number; errores_co: number; sin_match: number; sum_co: number; sum_es: number; sum_dif: number } }
interface Err { nit: string; nombre: string; saldo_1305: number; saldo_2805: number; tipo: string }
interface Prov { cuenta_es: string; nombre: string; saldo: number; tipo: string }

function ArApBadge({ estado }: { estado: string }) {
  const map: Record<string, string> = {
    CONCILIADO: "bg-emerald-100 text-emerald-700",
    DIFERENCIA: "bg-red-100 text-red-700",
    ERROR_CO: "bg-purple-100 text-purple-700",
    SIN_MATCH: "bg-slate-200 text-slate-600",
    PROVISIONAL_ES: "bg-orange-100 text-orange-700",
  };
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[estado] ?? "bg-slate-100"}`}>{estado}</span>;
}

const TABS = ["Conciliación", "Errores contables", "Provisionales (ES)"] as const;

export default function ArAp() {
  const [tab, setTab] = useState(0);
  return (
    <div>
      <PageHeader title="AR/AP — Cuentas por Cobrar y Pagar" subtitle="Conciliación de saldos por tercero (NIT ↔ NIF)" />
      <div className="flex gap-2 mb-4 border-b border-slate-200">
        {TABS.map((t, i) => (
          <button key={t} onClick={() => setTab(i)}
            className={`px-4 py-2 text-sm -mb-px border-b-2 ${tab === i ? "border-co text-co font-medium" : "border-transparent text-slate-500"}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === 0 && <Conciliacion />}
      {tab === 1 && <Errores />}
      {tab === 2 && <Provisionales />}
    </div>
  );
}

function Conciliacion() {
  const { data, loading, error, reload } = useFetch<Comp>("/api/ar-ap/comparativa");
  const [tipo, setTipo] = useState("");
  const [estado, setEstado] = useState("");
  const empty = !!data && data.filas.length === 0;
  const filas = useMemo(() => (data?.filas ?? []).filter((f) => (!tipo || f.tipo === tipo) && (!estado || f.estado === estado)), [data, tipo, estado]);

  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <Kpi label="Terceros" value={data.kpis.terceros} tone="blue" />
            <Kpi label="Conciliados" value={data.kpis.conciliados} tone="green" />
            <Kpi label="Diferencias" value={data.kpis.diferencias} tone="red" />
            <Kpi label="Errores CO" value={data.kpis.errores_co} tone="amber" />
            <Kpi label="Sin match" value={data.kpis.sin_match} />
          </div>
          <Card>
            <div className="flex gap-3 mb-3">
              <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="border rounded px-3 py-2 text-sm">
                <option value="">AR + AP</option><option value="AR">Cobrar (AR)</option><option value="AP">Pagar (AP)</option>
              </select>
              <select value={estado} onChange={(e) => setEstado(e.target.value)} className="border rounded px-3 py-2 text-sm">
                <option value="">Todos los estados</option>
                {["CONCILIADO", "DIFERENCIA", "ERROR_CO", "SIN_MATCH"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <span className="ml-auto self-center text-sm text-slate-400">{filas.length} terceros</span>
            </div>
            <div className="overflow-x-auto max-h-[58vh]">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                  <tr><th className="text-left py-2">Tercero</th><th className="text-left">NIT</th><th className="text-left">Tipo</th><th className="text-right">Saldo CO</th><th className="text-right">Saldo ES</th><th className="text-right">Diferencia</th><th className="text-left pl-3">Estado</th></tr>
                </thead>
                <tbody>
                  {filas.map((f, i) => (
                    <tr key={f.nit + f.tipo + i} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="py-2 max-w-[240px] truncate" title={f.nombre}>{f.nombre || "—"}</td>
                      <td className="font-mono text-xs">{f.nit || "—"}</td>
                      <td>{f.tipo}</td>
                      <td className="text-right tabular-nums">{fmtCOP(f.saldo_co)}</td>
                      <td className="text-right tabular-nums">{fmtCOP(f.saldo_es)}</td>
                      <td className={`text-right tabular-nums ${f.estado === "CONCILIADO" ? "text-emerald-600" : "text-red-600 font-medium"}`}>{fmtCOP(f.diferencia)}</td>
                      <td className="pl-3"><ArApBadge estado={f.estado} /></td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-slate-200 font-semibold">
                    <td className="py-2" colSpan={3}>Totales</td>
                    <td className="text-right tabular-nums">{fmtCOP(data.kpis.sum_co)}</td>
                    <td className="text-right tabular-nums">{fmtCOP(data.kpis.sum_es)}</td>
                    <td className="text-right tabular-nums">{fmtCOP(data.kpis.sum_dif)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        </>
      )}
    </DataState>
  );
}

function Errores() {
  const { data, loading, error, reload } = useFetch<Err[]>("/api/ar-ap/errores");
  const empty = !!data && data.length === 0;
  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      <Card>
        <p className="text-sm text-amber-700 bg-amber-50 rounded p-3 mb-4">
          Posible error de contabilización: saldo negativo en cuenta 1305. Verificar si debe reclasificarse a 2805 (anticipos de clientes).
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-slate-400">
            <tr><th className="text-left py-2">NIT</th><th className="text-left">Nombre</th><th className="text-right">Saldo 1305</th><th className="text-right">Saldo 2805</th></tr>
          </thead>
          <tbody>
            {(data ?? []).map((e, i) => (
              <tr key={e.nit + i} className="border-t border-slate-100">
                <td className="py-2 font-mono text-xs">{e.nit}</td>
                <td>{e.nombre}</td>
                <td className="text-right tabular-nums text-red-600">{fmtCOP(e.saldo_1305)}</td>
                <td className="text-right tabular-nums">{fmtCOP(e.saldo_2805)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </DataState>
  );
}

function Provisionales() {
  const { data, loading, error, reload } = useFetch<Prov[]>("/api/ar-ap/cuentas-amarillas");
  const empty = !!data && data.length === 0;
  return (
    <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
      <Card>
        <p className="text-sm text-orange-700 bg-orange-50 rounded p-3 mb-4">
          Estas cuentas (amarillas en el Excel) están pendientes de facturación y <b>no cruzan</b> con Colombia.
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-slate-400">
            <tr><th className="text-left py-2">Cuenta ES</th><th className="text-left">Nombre</th><th className="text-left">Tipo</th><th className="text-right">Saldo</th></tr>
          </thead>
          <tbody>
            {(data ?? []).map((p, i) => (
              <tr key={p.cuenta_es + i} className="border-t border-slate-100">
                <td className="py-2 font-mono text-xs">{p.cuenta_es} <span className="ml-1 px-2 py-0.5 rounded-full text-[10px] bg-orange-100 text-orange-700">PROVISIONAL</span></td>
                <td>{p.nombre}</td>
                <td>{p.tipo}</td>
                <td className="text-right tabular-nums">{fmtCOP(p.saldo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </DataState>
  );
}
