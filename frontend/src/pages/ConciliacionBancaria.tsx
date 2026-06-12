import { useEffect, useMemo, useRef, useState } from "react";
import type { ColDef } from "ag-grid-community";
import { api, descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";
import DataGrid from "../components/DataGrid";

interface Mov { id: number; fecha: string | null; concepto: string; documento: string; codigo: string; monto: number; match_tipo: string }
interface Conc { fecha_c: string | null; concepto_c: string; documento: string; monto: number; fecha_e: string | null; descripcion_e: string; match_tipo: string }
interface Recon {
  vacio?: boolean; mes: string; cuenta: string; estado: string;
  bloque_contable: { inicial: number; debito: number; credito: number; final: number; n_cargos: number; n_abonos: number };
  bloque_banco: { inicial: number; ingresos: number; egresos: number; final: number };
  bloque_conciliar: { saldo_libros: number; ing_no_libros: number; egr_no_libros: number; abonos_no_banco: number; cargos_no_banco: number; saldo_bancos: number; diferencia: number };
  conciliados: Conc[]; solo_libros: Mov[]; solo_banco: Mov[];
  kpis: { contable: number; extracto: number; conciliados: number; solo_libros: number; solo_banco: number; exactos: number };
}

function Linea({ label, value, signo }: { label: string; value: number; signo?: string }) {
  return (
    <div className="flex justify-between text-sm py-0.5">
      <span className="text-slate-500">{signo && <b className="mr-1">{signo}</b>}{label}</span>
      <span className={`tabular-nums ${value < 0 ? "text-red-600" : "text-slate-700"}`}>{fmtCOP(value)}</span>
    </div>
  );
}

function Upload({ origen, label, onDone }: { origen: string; label: string; onDone: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  async function up(file: File) {
    setBusy(true); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post(`/api/bancos/${origen}`, fd);
      setMsg({ ok: true, t: `${data.movimientos} mov · ${data.mes}` }); onDone();
    } catch (e: any) {
      setMsg({ ok: false, t: typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Error" });
    } finally { setBusy(false); if (ref.current) ref.current.value = ""; }
  }
  return (
    <div className="border rounded-lg p-3 bg-white">
      <div className="font-medium text-slate-700 text-sm mb-2">{label}</div>
      <input ref={ref} type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} />
      <button onClick={() => ref.current?.click()} disabled={busy} className="px-3 py-1.5 text-sm rounded bg-co text-white disabled:opacity-50">{busy ? "Procesando…" : "Elegir archivo"}</button>
      {msg && <p className={`text-xs mt-2 ${msg.ok ? "text-emerald-600" : "text-red-600"}`}>{msg.t}</p>}
    </div>
  );
}

export default function ConciliacionBancaria() {
  const { data, loading, error, reload } = useFetch<Recon>("/api/bancos/conciliacion");
  const [sc, setSc] = useState("");
  const [sb, setSb] = useState("");
  const [savingS, setSavingS] = useState(false);
  const vacio = !!data?.vacio;

  // precargar las casillas con los saldos iniciales actuales al cargar/cambiar de mes
  useEffect(() => {
    if (data && !data.vacio) {
      setSc(String(data.bloque_contable.inicial));
      setSb(String(data.bloque_banco.inicial));
    }
  }, [data?.mes, data?.bloque_contable.inicial, data?.bloque_banco.inicial]);

  async function guardarSaldos() {
    if (!data) return;
    setSavingS(true);
    try { await api.put("/api/bancos/saldos", { mes: data.mes, saldo_contable: Number(sc || 0), saldo_banco: Number(sb || 0) }); reload(); }
    catch (e: any) { alert(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Error al guardar"); }
    finally { setSavingS(false); }
  }
  async function cerrar() {
    if (!data || !window.confirm(`¿Cerrar la conciliación de ${data.mes}? Quedará como definitiva.`)) return;
    await api.post(`/api/bancos/cerrar?mes=${data.mes}`); reload();
  }
  async function reabrir() {
    if (!data) return;
    await api.post(`/api/bancos/reabrir?mes=${data.mes}`); reload();
  }

  const colsC = useMemo<ColDef[]>(() => [
    { field: "fecha_c", headerName: "Fecha contable", width: 130 },
    { field: "concepto_c", headerName: "Concepto contable", minWidth: 220, tooltipField: "concepto_c" },
    { field: "documento", headerName: "Doc", width: 110 },
    { field: "monto", headerName: "Monto", width: 140, type: "rightAligned", valueFormatter: (p: any) => fmtCOP(p.value) },
    { field: "fecha_e", headerName: "Fecha extracto", width: 130 },
    { field: "descripcion_e", headerName: "Descripción extracto", minWidth: 220, tooltipField: "descripcion_e" },
    { field: "match_tipo", headerName: "Cruce", width: 110, cellClass: (p: any) => (p.value === "exacto" ? "text-emerald-600" : "text-amber-600") },
  ], []);

  return (
    <div>
      <PageHeader title="Conciliación Bancaria" subtitle="Libros (contable) ↔ extracto bancario, mes a mes"
        action={data && !vacio ? (
          <div className="flex gap-2">
            <button onClick={() => descargarArchivo("/api/bancos/export", "conciliacion.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">📥 Exportar</button>
            {data.estado !== "cerrada"
              ? <button onClick={cerrar} className="px-3 py-1.5 text-sm bg-co text-white rounded">Cerrar conciliación</button>
              : <button onClick={reabrir} className="px-3 py-1.5 text-sm border border-amber-300 text-amber-700 rounded">Reabrir</button>}
          </div>
        ) : null} />

      <div className="grid md:grid-cols-2 gap-3 mb-4">
        <Upload origen="contable" label="1. Libro contable (BancosAtenea)" onDone={reload} />
        <Upload origen="extracto" label="2. Extracto bancario (Bancolombia)" onDone={reload} />
      </div>

      <DataState loading={loading} error={error} empty={vacio} onRetry={reload}>
        {data && !vacio && (
          <>
            <div className="text-sm text-slate-500 mb-3">Cuenta <b>{data.cuenta}</b> · Mes <b>{data.mes}</b> · Estado <b className={data.estado === "cerrada" ? "text-emerald-600" : "text-amber-600"}>{data.estado}</b></div>

            {/* Tres bloques */}
            <div className="grid md:grid-cols-3 gap-4 mb-4">
              <Card title="Saldos contables (libros)">
                <Linea label="Saldo inicial" value={data.bloque_contable.inicial} />
                <Linea label={`Débitos / ingresos (${data.bloque_contable.n_cargos})`} value={data.bloque_contable.debito} signo="+" />
                <Linea label={`Créditos / pagos (${data.bloque_contable.n_abonos})`} value={data.bloque_contable.credito} signo="−" />
                <div className="border-t mt-1 pt-1 font-semibold"><Linea label="Saldo final contable" value={data.bloque_contable.final} /></div>
              </Card>
              <Card title="Saldos bancarios (extracto)">
                <Linea label="Saldo inicial" value={data.bloque_banco.inicial} />
                <Linea label="Ingresos bancarios" value={data.bloque_banco.ingresos} signo="+" />
                <Linea label="Egresos bancarios" value={data.bloque_banco.egresos} signo="−" />
                <div className="border-t mt-1 pt-1 font-semibold"><Linea label="Saldo final bancario" value={data.bloque_banco.final} /></div>
              </Card>
              <Card title="Saldo por conciliar">
                <Linea label="Saldo en libros" value={data.bloque_conciliar.saldo_libros} />
                <Linea label="Ingresos extracto no en libros" value={data.bloque_conciliar.ing_no_libros} signo="+" />
                <Linea label="Egresos extracto no en libros" value={data.bloque_conciliar.egr_no_libros} signo="−" />
                <Linea label="Abonos contables no en banco" value={data.bloque_conciliar.abonos_no_banco} signo="−" />
                <Linea label="Cargos contables no en banco" value={data.bloque_conciliar.cargos_no_banco} signo="+" />
                <div className="border-t mt-1 pt-1 font-semibold"><Linea label="Saldo en bancos" value={data.bloque_conciliar.saldo_bancos} /></div>
                <div className={`mt-2 rounded p-2 text-sm font-semibold ${Math.abs(data.bloque_conciliar.diferencia) < 0.01 ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                  Diferencia en bancos: {fmtCOP(data.bloque_conciliar.diferencia)} {Math.abs(data.bloque_conciliar.diferencia) < 0.01 ? "✅ cuadra" : "⚠️"}
                </div>
              </Card>
            </div>

            {/* Saldos iniciales editables (siempre disponibles) */}
            <Card title="Saldos iniciales del mes (entrada manual)" className="mb-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="text-sm">Saldo contable inicial<br />
                  <input type="number" step="0.01" value={sc} onChange={(e) => setSc(e.target.value)} className="border rounded px-2 py-1 text-sm mt-1 w-44" /></label>
                <label className="text-sm">Saldo bancario inicial<br />
                  <input type="number" step="0.01" value={sb} onChange={(e) => setSb(e.target.value)} className="border rounded px-2 py-1 text-sm mt-1 w-44" /></label>
                <button onClick={guardarSaldos} disabled={savingS} className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded disabled:opacity-50">{savingS ? "Guardando…" : "Guardar saldos"}</button>
                {data.estado === "cerrada" && <span className="text-xs text-amber-600">La conciliación está cerrada; al guardar se recalculará igualmente.</span>}
              </div>
            </Card>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <Kpi label="Mov. contables" value={data.kpis.contable} />
              <Kpi label="Mov. extracto" value={data.kpis.extracto} />
              <Kpi label="Conciliados" value={data.kpis.conciliados} tone="green" hint={`${data.kpis.exactos} exactos`} />
              <Kpi label="Por conciliar" value={data.kpis.solo_libros + data.kpis.solo_banco} tone="amber" />
            </div>

            <Card title={`Conciliados (${data.conciliados.length})`} className="mb-4">
              <DataGrid gridId="banco-conciliados" columnDefs={colsC} rowData={data.conciliados} pageSize={50} height="42vh" />
            </Card>

            <div className="grid md:grid-cols-2 gap-4">
              <Card title={`En libros, no en banco (${data.solo_libros.length})`}>
                <SubTabla movs={data.solo_libros} campo="concepto" />
              </Card>
              <Card title={`En banco, no en libros (${data.solo_banco.length})`}>
                <SubTabla movs={data.solo_banco} campo="concepto" />
              </Card>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}

function SubTabla({ movs, campo }: { movs: Mov[]; campo: "concepto" }) {
  if (movs.length === 0) return <p className="text-sm text-emerald-600">Sin partidas. ✓</p>;
  return (
    <div className="overflow-auto max-h-[40vh]">
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white"><tr><th className="text-left py-1">Fecha</th><th className="text-left">Detalle</th><th className="text-right">Monto</th></tr></thead>
        <tbody>
          {movs.map((m) => (
            <tr key={m.id} className="border-t border-slate-100">
              <td className="py-1 whitespace-nowrap">{m.fecha ?? "—"}</td>
              <td className="max-w-[220px] truncate" title={m[campo]}>{m[campo] || "—"}</td>
              <td className={`text-right tabular-nums ${m.monto < 0 ? "text-red-600" : ""}`}>{fmtCOP(m.monto)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
