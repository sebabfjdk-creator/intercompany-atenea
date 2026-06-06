import { useRef, useState } from "react";
import { api } from "../api";
import { useFetch, rol } from "../lib/useFetch";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Estado {
  colombia_cuentas: number; espana_cuentas: number; homologacion_mappings: number;
  terceros: number; periodos: string[]; listo_para_comparativa: boolean;
}

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

  async function upload(file: File) {
    setBusy(true); setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/api/ingest/${tipo}`, fd);
      setMsg({ ok: true, text: `OK: ${JSON.stringify(data).slice(0, 160)}` });
      onDone();
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail ?? e?.message ?? "Error" });
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

export default function Ingesta() {
  const est = useFetch<Estado>("/api/estado-datos");
  const esAdminCo = rol() === "admin_co";

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
                disabled={esAdminCo && t.es} onDone={est.reload} />
            ))}
          </div>
        </Card>
        <p className="text-xs text-slate-400 mt-3">
          Los archivos no se almacenan: se parsean y se guardan solo las cifras agregadas por cuenta/periodo.
        </p>
      </DataState>
    </div>
  );
}
