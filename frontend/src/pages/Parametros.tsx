import { useEffect, useState } from "react";
import { api } from "../api";
import { useFetch, rol } from "../lib/useFetch";
import { fmtCOP, fmtPct } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Resp { tolerancia_abs_cop: number; tolerancia_pct: number }
const puedeEditar = ["admin", "admin_co"].includes(rol());

export default function Parametros() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/config/homologacion");
  const [abs, setAbs] = useState(0);
  const [pct, setPct] = useState(0);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => { if (data) { setAbs(data.tolerancia_abs_cop); setPct(data.tolerancia_pct); } }, [data]);

  async function guardar() {
    setSaving(true); setToast("");
    try {
      await api.put("/api/config/tolerancia", { tolerancia_abs_cop: abs, tolerancia_pct: pct });
      setToast("Parámetros guardados. Las conciliaciones se recalculan en vivo.");
      reload(); setTimeout(() => setToast(""), 4000);
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Error al guardar");
    } finally { setSaving(false); }
  }

  return (
    <div>
      <PageHeader title="Parámetros generales" subtitle="Umbrales de tolerancia de conciliación (aplican a Comparativa, Resumen y AR/AP)" />
      {toast && <div className="mb-4 bg-emerald-50 text-emerald-700 rounded p-3 text-sm">{toast}</div>}
      <DataState loading={loading} error={error} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <Kpi label="Tolerancia absoluta actual" value={fmtCOP(data.tolerancia_abs_cop)} tone="blue" />
              <Kpi label="Tolerancia % actual" value={fmtPct(data.tolerancia_pct)} tone="blue" />
            </div>
            <Card title="Editar tolerancias">
              {puedeEditar ? (
                <div className="space-y-4 max-w-md">
                  <div>
                    <label className="text-xs uppercase text-slate-400 block mb-1">Tolerancia absoluta (COP)</label>
                    <input type="number" value={abs} onChange={(e) => setAbs(Number(e.target.value))} className="border rounded px-3 py-2 w-full" />
                    <p className="text-xs text-slate-400 mt-1">Una diferencia |dif| ≤ este valor se considera conciliada.</p>
                  </div>
                  <div>
                    <label className="text-xs uppercase text-slate-400 block mb-1">Tolerancia porcentual (0–1)</label>
                    <input type="number" step="0.001" value={pct} onChange={(e) => setPct(Number(e.target.value))} className="border rounded px-3 py-2 w-full" />
                    <p className="text-xs text-slate-400 mt-1">Ej.: 0.005 = 0,5% sobre la base mayor.</p>
                  </div>
                  <button onClick={guardar} disabled={saving} className="px-4 py-2 bg-emerald-600 text-white rounded">
                    {saving ? "Guardando…" : "Guardar parámetros"}
                  </button>
                </div>
              ) : (
                <p className="text-sm text-slate-400">Tu rol es de solo lectura sobre los parámetros.</p>
              )}
            </Card>
          </>
        )}
      </DataState>
    </div>
  );
}
