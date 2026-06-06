import { useFetch } from "../lib/useFetch";
import { fmtCOP, fmtPct } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Grupo { grupo: string; tipo: string; tipo_relacion: string; cuentas_co: string[]; cuentas_es: string[] }
interface Resp { grupos: Grupo[]; tolerancia_abs_cop: number; tolerancia_pct: number }

export default function Config() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/config/homologacion");
  const empty = !!data && data.grupos.length === 0;

  return (
    <div>
      <PageHeader title="Configuración" subtitle="Homologación de cuentas y umbrales de tolerancia" />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <Kpi label="Grupos homologados" value={data.grupos.length} tone="blue" />
              <Kpi label="Tolerancia absoluta" value={fmtCOP(data.tolerancia_abs_cop)} />
              <Kpi label="Tolerancia %" value={fmtPct(data.tolerancia_pct)} />
            </div>
            <Card title="Tabla de homologación (CO ↔ ES)">
              <div className="overflow-x-auto max-h-[64vh]">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                    <tr><th className="text-left py-2">Grupo</th><th className="text-left">Tipo</th><th className="text-left">Relación</th><th className="text-left">Cuentas Colombia</th><th className="text-left">Cuentas España</th></tr>
                  </thead>
                  <tbody>
                    {data.grupos.map((g, i) => (
                      <tr key={g.grupo + i} className="border-t border-slate-100 align-top">
                        <td className="py-2 max-w-[200px] truncate font-medium" title={g.grupo}>{g.grupo}</td>
                        <td className="capitalize">{g.tipo}</td>
                        <td><span className="text-xs px-2 py-0.5 rounded bg-slate-100">{g.tipo_relacion}</span></td>
                        <td className="font-mono text-xs">{g.cuentas_co.join(", ") || "—"}</td>
                        <td className="font-mono text-xs">{g.cuentas_es.join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <p className="text-xs text-slate-400 mt-3">La edición de la homologación desde la app es una mejora prevista; hoy se gestiona vía el archivo de homologación en Ingesta.</p>
          </>
        )}
      </DataState>
    </div>
  );
}
