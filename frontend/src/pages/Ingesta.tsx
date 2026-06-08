import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
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
  id: number; tipo: string; tipo_label: string; archivo: string; periodo: string; usuario: string;
  fecha: string | null; registros: number; estado: string; observaciones: string;
}

interface Periodo { pais: string; periodo: string; cuentas: number; movimientos: number }

// tipo de tarjeta (endpoint de subida) -> tipo registrado en file_upload
const HIST_TIPO: Record<string, string> = {
  homologacion: "homologacion", terceros: "terceros", colombia: "colombia", espana: "espana",
  "ar-ap/colombia": "arap_co", "ar-ap/espana": "arap_es",
};

const TIPOS = [
  { id: "homologacion", label: "Homologación de cuentas", hint: "Hoja Gastos/Ingresos + Puente Terceros", es: true },
  { id: "terceros", label: "Puente de terceros (NIF↔NIT)", hint: "Mismo archivo de homologación", es: true },
  { id: "colombia", label: "Colombia (Siesa)", hint: "Balances Enero y Feb–Marzo", es: false },
  { id: "espana", label: "España (DELSOL)", hint: "Libro Mayor Enero y Feb–Marzo", es: true },
];

function fmtFecha(s: string | null) {
  return s ? new Date(s).toLocaleString("es-CO") : "—";
}

function EstadoBadge({ estado }: { estado: string }) {
  const map: Record<string, { txt: string; cls: string }> = {
    cargado: { txt: "🟢 Procesado correctamente", cls: "text-emerald-600" },
    reemplazado: { txt: "⚪ Reemplazado", cls: "text-slate-400" },
    eliminado: { txt: "🔴 Eliminado", cls: "text-red-500" },
    fallido: { txt: "🔴 Error de procesamiento", cls: "text-red-600" },
  };
  const e = map[estado] ?? { txt: estado, cls: "text-slate-500" };
  return <span className={`text-xs ${e.cls}`}>{e.txt}</span>;
}

// Botón circular de acción (estilo SaaS enterprise: hover suave + sombra + tooltip)
function IconBtn({ title, disabled, onClick, children }: { title: string; disabled?: boolean; onClick?: () => void; children: ReactNode }) {
  return (
    <button title={title} onClick={onClick} disabled={disabled}
      className="w-8 h-8 rounded-full border border-slate-200 bg-white shadow-sm flex items-center justify-center text-sm
                 transition hover:bg-slate-50 hover:shadow disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none">
      {children}
    </button>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <h3 className="font-semibold text-slate-700">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-lg leading-none">×</button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

function Uploader({ tipo, label, hint, disabled, cargas, onDone, onEdit, onDelete }: {
  tipo: string; label: string; hint: string; disabled: boolean; cargas: Carga[];
  onDone: () => void; onEdit: (c: Carga) => void; onDelete: (c: Carga) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [verOpen, setVerOpen] = useState(false);
  const [histOpen, setHistOpen] = useState(false);

  const activa = cargas.find((c) => c.estado === "cargado") ?? null;  // más reciente activa

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
      setMsg({ ok: true, text: `Cargado: ${data.archivo ?? file.name}` });
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
    <div className={`border rounded-lg p-4 ${disabled ? "opacity-60 bg-slate-50" : "bg-white"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium text-slate-700">{label}</div>
          <div className="text-xs text-slate-400">{hint}</div>
        </div>
        {/* Barra de acciones rápida (esquina superior derecha) */}
        <div className="flex gap-1 shrink-0">
          <IconBtn title={activa ? "Ver archivo cargado" : "No existe archivo cargado"} disabled={!activa} onClick={() => setVerOpen(true)}>📎</IconBtn>
          <IconBtn title={activa ? "Editar información" : "No existe archivo cargado"} disabled={!activa} onClick={() => activa && onEdit(activa)}>✏️</IconBtn>
          <IconBtn title={disabled ? "Sin permiso" : activa ? "Reemplazar archivo" : "No existe archivo cargado"} disabled={disabled || !activa} onClick={() => ref.current?.click()}>🔄</IconBtn>
          <IconBtn title={disabled ? "Sin permiso" : activa ? "Eliminar archivo" : "No existe archivo cargado"} disabled={disabled || !activa} onClick={() => activa && onDelete(activa)}>🗑️</IconBtn>
          <IconBtn title={cargas.length ? "Historial" : "Sin historial"} disabled={cargas.length === 0} onClick={() => setHistOpen(true)}>📜</IconBtn>
        </div>
      </div>

      {/* Archivo activo + estado (sin abrir ventanas) */}
      {activa && (
        <div className="mt-2 flex items-center gap-2 text-sm">
          <span className="truncate text-slate-600" title={activa.archivo}>📄 {activa.archivo || "(sin nombre)"}</span>
          <EstadoBadge estado={activa.estado} />
        </div>
      )}

      <input ref={ref} type="file" accept=".xlsx,.xls" className="hidden"
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      <button onClick={() => ref.current?.click()} disabled={disabled || busy}
        className="mt-3 px-3 py-1.5 text-sm rounded bg-co text-white disabled:opacity-50 disabled:cursor-not-allowed">
        {busy ? "Procesando…" : activa ? "Subir otro archivo" : "Elegir archivo"}
      </button>
      {disabled && <p className="text-xs text-amber-600 mt-2">Tu rol (admin_co) no puede modificar datos de España.</p>}
      {msg && <p className={`text-xs mt-2 ${msg.ok ? "text-emerald-600" : "text-red-600"}`}>{msg.text}</p>}

      {verOpen && activa && (
        <Modal title="Detalle del archivo" onClose={() => setVerOpen(false)}>
          <dl className="grid grid-cols-3 gap-y-2 text-sm">
            <dt className="text-slate-400">Archivo</dt><dd className="col-span-2 break-all">{activa.archivo || "—"}</dd>
            <dt className="text-slate-400">Proceso</dt><dd className="col-span-2">{activa.tipo_label}</dd>
            <dt className="text-slate-400">Periodo</dt><dd className="col-span-2 font-mono">{activa.periodo || "—"}</dd>
            <dt className="text-slate-400">Usuario</dt><dd className="col-span-2">{activa.usuario}</dd>
            <dt className="text-slate-400">Fecha</dt><dd className="col-span-2">{fmtFecha(activa.fecha)}</dd>
            <dt className="text-slate-400">Registros</dt><dd className="col-span-2 tabular-nums">{activa.registros.toLocaleString("es-CO")}</dd>
            <dt className="text-slate-400">Estado</dt><dd className="col-span-2"><EstadoBadge estado={activa.estado} /></dd>
            <dt className="text-slate-400">Observaciones</dt><dd className="col-span-2 whitespace-pre-wrap">{activa.observaciones || "—"}</dd>
          </dl>
          <p className="text-xs text-slate-400 mt-4">El archivo no se almacena (solo metadatos + hash); por eso no se muestra tamaño/descarga.</p>
        </Modal>
      )}

      {histOpen && (
        <Modal title={`Historial — ${label}`} onClose={() => setHistOpen(false)}>
          {cargas.length === 0 ? <p className="text-sm text-slate-400">Sin movimientos.</p> : (
            <ul className="space-y-2">
              {cargas.map((c) => (
                <li key={c.id} className="flex items-start gap-2 text-sm border-b border-slate-50 pb-2">
                  <span className="mt-0.5"><EstadoBadge estado={c.estado} /></span>
                  <div className="min-w-0">
                    <div className="truncate text-slate-700" title={c.archivo}>{c.archivo || "(sin nombre)"} · <span className="font-mono text-xs">{c.periodo || "—"}</span></div>
                    <div className="text-xs text-slate-400">{c.usuario} · {fmtFecha(c.fecha)} · {c.registros.toLocaleString("es-CO")} reg.</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
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

  // modales de edición / eliminación (estilo enterprise)
  const [edit, setEdit] = useState<Carga | null>(null);
  const [editText, setEditText] = useState("");
  const [del, setDel] = useState<Carga | null>(null);
  const [saving, setSaving] = useState(false);

  const cargasDe = (tipoCard: string) => (hist.data ?? []).filter((c) => c.tipo === HIST_TIPO[tipoCard]);

  function openEdit(c: Carga) { setEdit(c); setEditText(c.observaciones || ""); }
  async function saveEdit() {
    if (!edit) return;
    setSaving(true);
    try { await api.put(`/api/ingest/archivos/${edit.id}`, { observaciones: editText }); setEdit(null); hist.reload(); }
    catch (e: any) { alert(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Error al guardar"); }
    finally { setSaving(false); }
  }
  async function confirmDelete() {
    if (!del) return;
    setSaving(true);
    try { await api.delete(`/api/ingest/archivos/${del.id}`); setDel(null); reloadAll(); }
    catch (e: any) { alert(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Error al eliminar"); }
    finally { setSaving(false); }
  }

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
                disabled={esAdminCo && t.es} cargas={cargasDe(t.id)} onDone={reloadAll}
                onEdit={openEdit} onDelete={setDel} />
            ))}
          </div>
        </Card>
        <Card title="Cuentas por Cobrar y Pagar (AR/AP)" className="mt-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Uploader tipo="ar-ap/colombia" label="Colombia AR/AP"
              hint="Cartera/CXP Siesa (1305, 2805, 22xx)" disabled={false} cargas={cargasDe("ar-ap/colombia")}
              onDone={reloadAll} onEdit={openEdit} onDelete={setDel} />
            <Uploader tipo="ar-ap/espana" label="España AR/AP"
              hint="Cartera/CXP DELSOL (430, 410)" disabled={esAdminCo} cargas={cargasDe("ar-ap/espana")}
              onDone={reloadAll} onEdit={openEdit} onDelete={setDel} />
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

        <Card title="Historial de cargas (global)" className="mt-4">
          {hist.data && hist.data.length > 0 ? (
            <DataGrid gridId="ingesta-historial" columnDefs={cols} rowData={hist.data} pageSize={50} height="48vh"
              context={{ onEdit: openEdit, onDelete: setDel }} />
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

      {/* Modal Editar (solo observaciones; nunca datos contables) */}
      {edit && (
        <Modal title="Editar información" onClose={() => setEdit(null)}>
          <div className="text-sm text-slate-500 mb-2">{edit.tipo_label} · <span className="font-mono">{edit.periodo || "—"}</span></div>
          <label className="text-xs text-slate-400">Observaciones / comentarios internos</label>
          <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={4}
            className="w-full border rounded px-3 py-2 text-sm mt-1" placeholder="Notas para auditoría… (no modifica datos contables)" />
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setEdit(null)} className="px-3 py-1.5 text-sm bg-slate-200 rounded">Cancelar</button>
            <button onClick={saveEdit} disabled={saving} className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded">{saving ? "Guardando…" : "Guardar"}</button>
          </div>
        </Modal>
      )}

      {/* Modal Eliminar */}
      {del && (
        <Modal title="Eliminar archivo" onClose={() => setDel(null)}>
          <p className="text-sm text-slate-600">¿Está seguro de eliminar este archivo?</p>
          <div className="bg-slate-50 rounded p-3 mt-2 text-sm">
            <div className="font-medium text-slate-700">{del.archivo || "(sin nombre)"}</div>
            <div className="text-xs text-slate-400">{del.tipo_label} · {del.periodo || "—"} · {del.registros.toLocaleString("es-CO")} registros</div>
          </div>
          <p className="text-xs text-slate-500 mt-3">Esta acción eliminará el registro de carga y los <b>datos contables asociados</b> del periodo. La conciliación se recalcula automáticamente.</p>
          <div className="flex justify-end gap-2 mt-4">
            <button onClick={() => setDel(null)} className="px-3 py-1.5 text-sm bg-slate-200 rounded">Cancelar</button>
            <button onClick={confirmDelete} disabled={saving} className="px-3 py-1.5 text-sm bg-red-600 text-white rounded">{saving ? "Eliminando…" : "Eliminar"}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
