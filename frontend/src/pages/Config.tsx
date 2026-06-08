import { useMemo, useState } from "react";
import { api, API_BASE } from "../api";
import { useFetch, rol } from "../lib/useFetch";
import { fmtCOP, fmtPct } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Grupo {
  id?: number | null; grupo: string; tipo: string; tipo_relacion: string;
  cuentas_co: string[]; cuentas_es: string[];
}
interface Resp { grupos: Grupo[]; tolerancia_abs_cop: number; tolerancia_pct: number }

const TIPOS = ["gasto", "ingreso", "activo", "pasivo"];
const RELS = ["directa", "n_a_n", "sin_par"];
const puedeEditar = ["admin", "admin_co"].includes(rol());

function TagInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [txt, setTxt] = useState("");
  function add() {
    const parts = txt.split(",").map((s) => s.trim()).filter(Boolean);
    const validos = parts.filter((p) => /^[\d.]+[x*]?$|^\d[\d.]*$/i.test(p));
    if (validos.length) onChange([...new Set([...value, ...validos])]);
    setTxt("");
  }
  return (
    <div className="flex flex-wrap gap-1 items-center">
      {value.map((c) => (
        <span key={c} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-100 text-xs font-mono">
          {c}<button onClick={() => onChange(value.filter((x) => x !== c))} className="text-slate-400 hover:text-red-600">×</button>
        </span>
      ))}
      <input value={txt} onChange={(e) => setTxt(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }}
        onBlur={add} placeholder="+ código" className="border rounded px-1 py-0.5 text-xs w-20" />
    </div>
  );
}

export default function Config() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/config/homologacion");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Grupo[]>([]);
  const [tolAbs, setTolAbs] = useState(0);
  const [tolPct, setTolPct] = useState(0);
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [changes, setChanges] = useState(0);
  const empty = !!data && data.grupos.length === 0;

  function startEdit() {
    if (!data) return;
    setDraft(data.grupos.map((g) => ({ ...g, cuentas_co: [...g.cuentas_co], cuentas_es: [...g.cuentas_es] })));
    setTolAbs(data.tolerancia_abs_cop); setTolPct(data.tolerancia_pct);
    setChanges(0); setEditing(true);
  }
  function upd(i: number, patch: Partial<Grupo>) {
    setDraft((d) => d.map((g, j) => (j === i ? { ...g, ...patch } : g)));
    setChanges((c) => c + 1);
  }
  function delGrupo(i: number) {
    if (!confirm(`¿Eliminar el grupo "${draft[i].grupo}"?`)) return;
    setDraft((d) => d.filter((_, j) => j !== i)); setChanges((c) => c + 1);
  }
  function addGrupo() {
    setDraft((d) => [...d, { grupo: "", tipo: "gasto", tipo_relacion: "n_a_n", cuentas_co: [], cuentas_es: [] }]);
    setChanges((c) => c + 1);
  }
  async function guardar() {
    if (!confirm("¿Guardar cambios en la homologación? Esto recalculará Comparativa, Resumen y Excepciones.")) return;
    setSaving(true);
    try {
      await api.put("/api/config/homologacion", { grupos: draft });
      await api.put("/api/config/tolerancia", { tolerancia_abs_cop: tolAbs, tolerancia_pct: tolPct });
      setEditing(false); setToast("Homologación actualizada. Las tablas han sido recalculadas.");
      reload(); setTimeout(() => setToast(""), 4000);
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Error al guardar");
    } finally { setSaving(false); }
  }

  const filas = useMemo(() => {
    const src = editing ? draft : (data?.grupos ?? []);
    const q = search.toLowerCase();
    return src.map((g, i) => ({ g, i })).filter(({ g }) =>
      !q || g.grupo.toLowerCase().includes(q) || g.cuentas_co.join(",").includes(q) || g.cuentas_es.join(",").includes(q));
  }, [editing, draft, data, search]);

  return (
    <div>
      <PageHeader title="Configuración" subtitle="Homologación de cuentas y umbrales de tolerancia"
        action={puedeEditar && !editing && data ? (
          <div className="flex gap-2">
            <a href={`${API_BASE}/api/config/homologacion/export`} className="px-3 py-2 text-sm border rounded text-slate-600">⬇️ Exportar</a>
            <button onClick={startEdit} className="px-3 py-2 text-sm bg-co text-white rounded">✏️ Editar homologación</button>
          </div>
        ) : null} />

      {toast && <div className="mb-4 bg-emerald-50 text-emerald-700 rounded p-3 text-sm">{toast}</div>}
      {editing && <div className="mb-4 bg-amber-50 text-amber-700 rounded p-3 text-sm">Estás en modo edición. Los cambios guardados afectarán Comparativa, Resumen, Terceros y Excepciones.</div>}

      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Kpi label="Grupos homologados" value={(editing ? draft : data.grupos).length} tone="blue" />
              {editing ? (
                <>
                  <div className="bg-white rounded-xl border p-4">
                    <div className="text-xs uppercase text-slate-400">Tolerancia absoluta</div>
                    <input type="number" value={tolAbs} onChange={(e) => setTolAbs(Number(e.target.value))} className="border rounded px-2 py-1 mt-1 w-full text-lg font-bold" />
                  </div>
                  <div className="bg-white rounded-xl border p-4">
                    <div className="text-xs uppercase text-slate-400">Tolerancia % (0-1)</div>
                    <input type="number" step="0.001" value={tolPct} onChange={(e) => setTolPct(Number(e.target.value))} className="border rounded px-2 py-1 mt-1 w-full text-lg font-bold" />
                  </div>
                </>
              ) : (
                <>
                  <Kpi label="Tolerancia absoluta" value={fmtCOP(data.tolerancia_abs_cop)} />
                  <Kpi label="Tolerancia %" value={fmtPct(data.tolerancia_pct)} />
                </>
              )}
            </div>

            <Card title="Tabla de homologación (CO ↔ ES)">
              <div className="flex items-center gap-3 mb-3">
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar grupo o código…" className="border rounded px-3 py-2 text-sm flex-1" />
                {editing && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">{changes} cambios sin guardar</span>
                    <button onClick={addGrupo} className="px-3 py-2 text-sm border rounded">+ Nuevo grupo</button>
                    <button onClick={() => setEditing(false)} className="px-3 py-2 text-sm bg-slate-200 rounded">Cancelar</button>
                    <button onClick={guardar} disabled={saving} className="px-3 py-2 text-sm bg-emerald-600 text-white rounded">{saving ? "Guardando…" : "Guardar cambios"}</button>
                  </div>
                )}
              </div>
              <div className="overflow-x-auto max-h-[60vh]">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                    <tr><th className="text-left py-2">Grupo</th><th className="text-left">Tipo</th><th className="text-left">Relación</th><th className="text-left">Cuentas Colombia</th><th className="text-left">Cuentas España</th>{editing && <th></th>}</tr>
                  </thead>
                  <tbody>
                    {filas.map(({ g, i }) => (
                      <tr key={i} className="border-t border-slate-100 align-top">
                        <td className="py-2 max-w-[200px]">
                          {editing ? <input value={g.grupo} onChange={(e) => upd(i, { grupo: e.target.value })} className="border rounded px-2 py-1 w-full text-sm" />
                            : <span className="font-medium truncate" title={g.grupo}>{g.grupo}</span>}
                        </td>
                        <td>{editing ? <select value={g.tipo} onChange={(e) => upd(i, { tipo: e.target.value })} className="border rounded px-1 py-1 text-sm">{TIPOS.map((t) => <option key={t}>{t}</option>)}</select> : <span className="capitalize">{g.tipo}</span>}</td>
                        <td>{editing ? <select value={g.tipo_relacion} onChange={(e) => upd(i, { tipo_relacion: e.target.value })} className="border rounded px-1 py-1 text-sm">{RELS.map((t) => <option key={t}>{t}</option>)}</select> : <span className="text-xs px-2 py-0.5 rounded bg-slate-100">{g.tipo_relacion}</span>}</td>
                        <td className="font-mono text-xs">{editing ? <TagInput value={g.cuentas_co} onChange={(v) => upd(i, { cuentas_co: v })} /> : g.cuentas_co.join(", ") || "—"}</td>
                        <td className="font-mono text-xs">{editing ? <TagInput value={g.cuentas_es} onChange={(v) => upd(i, { cuentas_es: v })} /> : g.cuentas_es.join(", ") || "—"}</td>
                        {editing && <td><button onClick={() => delGrupo(i)} className="text-red-500 hover:text-red-700" title="Eliminar">🗑️</button></td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            {!puedeEditar && <p className="text-xs text-slate-400 mt-3">Tu rol es de solo lectura sobre la configuración.</p>}
          </>
        )}
      </DataState>
    </div>
  );
}
