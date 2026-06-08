import { useMemo, useRef, useState } from "react";
import type { ColDef } from "ag-grid-community";
import { api } from "../api";
import { useFetch, rol } from "../lib/useFetch";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";
import DataGrid from "../components/DataGrid";

interface Estado {
  colombia_cuentas: number; espana_cuentas: number; homologacion_mappings: number;
  terceros: number; periodos: string[]; listo_para_comparativa: boolean;
}

interface Carga {
  id: number; tipo_label: string; archivo: string; periodo: string; usuario: string;
  fecha: string | null; registros: number; estado: string; observaciones: string;
}

interface Periodo { pais: string; periodo: string; cuentas: number; movimientos: number }

const TIPOS = [
  { id: "homologacion", label: "Homologación de cuentas", hint: "Hoja Gastos/Ingresos + Puente Terceros", es: true },
  { id: "terceros", label: "Puente de terceros (NIF↔NIT)", hint: "Mismo archivo de homologación", es: true },
  { id: "colombia", label: "Colombia (Siesa)", hint: "Balances Enero y Feb–Marzo", es: false },
  { id: "espana", label: "España (DELSOL)", hint: "Libro Mayor Enero y Feb–Marzo", es: true },
];

function Uploader({ tipo, label, hint, disabled, onDone }: { tipo: string; label: string; hint: string; disabled: boolean; onDone: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function errText(d: any): string {
    if (typeof d === "string") return d;
    if (d?.mensaje) return d.mensaje;
    return d ? JSON.stringify(d) : "Error";
  }

  async function upload(file: File, replace = false) {
    setBusy(true); setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const url = `/api/ingest/${tipo}${replace ? "?replace=true" : ""}`;
      const { data } = await api.post(url, fd);
      setMsg({ ok: true, text: `OK: ${JSON.stringify(data).slice(0, 160)}` });
      onDone();
    } catch (e: any) {
      const det = e?.response?.data?.detail;
      if (e?.response?.status === 409 && !replace) {
        const m = det?.mensaje ?? "Ya existe información para este periodo. ¿Reemplazar?";
        if (window.confirm(m)) { await upload(file, true); return; }
        setMsg({ ok: false, text: "Carga cancelada (no se reemplazó)." });
      } else {
        setMsg({ ok: false, text: errText(det) || e?.message || "Error" });
      }
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div className={`border rounded-lg p-4 ${disabled ? "opacity-50 bg-slate-50" : "bg-white"}`}>
      <div className="font-medium text-slate-700">{label}</div>
      <div className="text-xs text-slate-400 mb-3">{hint}</div>
      <input ref={ref} type="file" accept=".xlsx,.xls" disabled={disabled || busy}
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
        className="block w-full text-sm text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-co file:text-white file:text-sm disabled:cursor-not-allowed" />
      {disabled && <p className="text-xs text-amber-600 mt-2">Tu rol (admin_co) no puede modificar datos de España.</p>}
      {busy && <p className="text-xs text-slate-500 mt-2">Procesando…</p>}
      {msg && <p className={`text-xs mt-2 ${msg.ok ? "text-emerald-600" : "text-red-600"}`}>{msg.text}</p>}
    </div>
  );
}

function AccionesCell(p: any) {
  const r = p.data as Carga;
  const ctx = p.context || {};
  return (
    <div className="flex gap-2 items-center h-full">
      <button title="Editar observaciones" onClick={() => ctx.onEdit?.(r)} className="hover:opacity-60">✏️</button>
      {r.estado !== "eliminado" && (
        <button title="Eliminar carga y registros" onClick={() => ctx.onDelete?.(r)} className="hover:opacity-60">🗑️</button>
      )}
    </div>
  );
}

export default function Ingesta() {
  const est = useFetch<Estado>("/api/estado-datos");
  const hist = useFetch<Carga[]>("/api/ingest/archivos");
  const pers = useFetch<Periodo[]>("/api/ingest/periodos");
  const esAdminCo = rol() === "admin_co";
  const reloadAll = () => { est.reload(); hist.reload(); pers.reload(); };

  async function onDeletePeriodo(p: Periodo) {
    const pais = p.pais === "ES" ? "España" : "Colombia";
    if (!window.confirm(`Eliminar el periodo ${p.periodo} de ${pais} (${p.cuentas} cuentas, ${p.movimientos} movimientos). Esta acción borra los balances PYG de ese periodo. ¿Continuar?`)) return;
    try {
      await api.delete(`/api/ingest/periodo?pais=${encodeURIComponent(p.pais)}&periodo=${encodeURIComponent(p.periodo)}`);
      reloadAll();
    } catch (e: any) {
      alert(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Error al eliminar el periodo");
    }
  }

  async function onEditObs(r: Carga) {
    const obs = window.prompt("Observaciones / comentarios (no modifica datos contables):", r.observaciones || "");
    if (obs === null) return;
    try { await api.put(`/api/ingest/archivos/${r.id}`, { observaciones: obs }); hist.reload(); }
    catch (e: any) { alert(e?.response?.data?.detail ?? "Error al guardar"); }
  }
  async function onDeleteCarga(r: Carga) {
    if (!window.confirm(`Esta acción eliminará "${r.archivo}" (${r.tipo_label} ${r.periodo}) y TODOS los registros asociados. ¿Desea continuar?`)) return;
    try { await api.delete(`/api/ingest/archivos/${r.id}`); reloadAll(); }
    catch (e: any) { alert(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Error al eliminar"); }
  }

  const cols = useMemo<ColDef[]>(() => [
    { field: "tipo_label", headerName: "Tipo", width: 170, pinned: "left" },
    { field: "archivo", headerName: "Archivo", minWidth: 220, tooltipField: "archivo" },
    { field: "periodo", headerName: "Periodo", width: 130 },
    { field: "usuario", headerName: "Usuario", width: 180 },
    { field: "fecha", headerName: "Fecha", width: 170,
      valueFormatter: (p: any) => (p.value ? new Date(p.value).toLocaleString("es-CO") : "—") },
    { field: "registros", headerName: "Registros", width: 120, type: "rightAligned" },
    { field: "estado", headerName: "Estado", width: 130,
      cellClass: (p: any) => p.value === "cargado" ? "text-emerald-600 font-medium"
        : p.value === "reemplazado" ? "text-slate-400" : "text-amber-600" },
    { field: "observaciones", headerName: "Observaciones", minWidth: 180, tooltipField: "observaciones" },
    { headerName: "Acciones", width: 110, pinned: "right", sortable: false, filter: false,
      cellRenderer: AccionesCell },
  ], []);

  return (
    <div>
      <PageHeader title="Ingesta de archivos" subtitle="Sube los Excel para poblar la conciliación. El cierre del periodo es automático." />
      <DataState loading={est.loading} error={est.error} onRetry={est.reload}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Kpi label="Cuentas Colombia" value={est.data?.colombia_cuentas ?? 0} tone="blue" />
          <Kpi label="Cuentas España" value={est.data?.espana_cuentas ?? 0} tone="red" />
          <Kpi label="Mapeos homolog." value={est.data?.homologacion_mappings ?? 0} />
          <Kpi label="Terceros" value={est.data?.terceros ?? 0} tone="green" />
        </div>
        <Card title="Subir archivos (orden sugerido: homologación → terceros → Colombia → España)">
          <div className="grid md:grid-cols-2 gap-4">
            {TIPOS.map((t) => (
              <Uploader key={t.id} tipo={t.id} label={t.label} hint={t.hint}
                disabled={esAdminCo && t.es} onDone={reloadAll} />
            ))}
          </div>
        </Card>
        <Card title="Cuentas por Cobrar y Pagar (AR/AP)" className="mt-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Uploader tipo="ar-ap/colombia" label="Colombia AR/AP"
              hint="Cartera/CXP Siesa (1305, 2805, 22xx)" disabled={false} onDone={reloadAll} />
            <Uploader tipo="ar-ap/espana" label="España AR/AP"
              hint="Cartera/CXP DELSOL (430, 410)" disabled={esAdminCo} onDone={reloadAll} />
          </div>
          <p className="text-xs text-slate-400 mt-3">
            Puedes subir el mismo archivo (CarteraYPasivos) en ambos slots: cada uno toma sus hojas
            (Atenea = España, Neuron = Colombia). Las cuentas amarillas (provisionales) no cruzan.
          </p>
        </Card>

        <Card title="Periodos cargados (balances PYG)" className="mt-4">
          {pers.data && pers.data.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-slate-400 border-b border-slate-100">
                <tr>
                  <th className="text-left py-2">País</th>
                  <th className="text-left">Periodo</th>
                  <th className="text-right">Cuentas</th>
                  <th className="text-right">Movimientos</th>
                  <th className="text-right pr-1">Acción</th>
                </tr>
              </thead>
              <tbody>
                {pers.data.map((p) => (
                  <tr key={`${p.pais}-${p.periodo}`} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2">
                      <span className={p.pais === "ES" ? "text-es font-medium" : "text-co font-medium"}>
                        {p.pais === "ES" ? "España" : "Colombia"}
                      </span>
                    </td>
                    <td className="font-mono">{p.periodo}</td>
                    <td className="text-right tabular-nums">{p.cuentas.toLocaleString("es-CO")}</td>
                    <td className="text-right tabular-nums">{p.movimientos.toLocaleString("es-CO")}</td>
                    <td className="text-right pr-1">
                      <button onClick={() => onDeletePeriodo(p)} disabled={esAdminCo && p.pais === "ES"}
                        className="px-2 py-1 text-xs border rounded text-red-600 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        title={esAdminCo && p.pais === "ES" ? "admin_co no puede borrar datos de España" : "Eliminar este periodo"}>
                        🗑️ Eliminar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-400">No hay periodos PYG cargados.</p>
          )}
          <p className="text-xs text-slate-400 mt-3">
            Elimina aquí un periodo completo (p.ej. <b>2026-02-03</b>) sin tocar los demás. Útil para
            re-cargar Febrero y Marzo por separado cuando dispongas de balances mensuales.
          </p>
        </Card>

        <Card title="Historial de cargas" className="mt-4">
          {hist.data && hist.data.length > 0 ? (
            <DataGrid gridId="ingesta-historial" columnDefs={cols} rowData={hist.data} pageSize={50} height="48vh"
              context={{ onEdit: onEditObs, onDelete: onDeleteCarga }} />
          ) : (
            <p className="text-sm text-slate-400">Aún no hay cargas registradas. Al subir un archivo aparecerá aquí con su periodo, usuario y fecha.</p>
          )}
        </Card>

        <p className="text-xs text-slate-400 mt-3">
          Los archivos no se almacenan: se parsean y se guardan solo las cifras agregadas por cuenta/periodo.
          El historial registra qué se cargó, de qué periodo, quién y cuándo (una recarga del mismo
          tipo y periodo marca la anterior como “reemplazado”).
        </p>
      </DataState>
    </div>
  );
}
