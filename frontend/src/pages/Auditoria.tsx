import { useFetch } from "../lib/useFetch";
import { PageHeader, Card, DataState } from "../components/ui";

interface Log { entidad: string; entidad_id: string; accion: string; valor_despues: string | null; usuario_id: number | null; ts: string | null }

export default function Auditoria() {
  const { data, loading, error, reload } = useFetch<Log[]>("/api/auditoria");
  const empty = !!data && data.length === 0;

  return (
    <div>
      <PageHeader title="Auditoría" subtitle="Registro inmutable de cambios (quién, qué, cuándo)" />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <Card>
            <div className="overflow-x-auto max-h-[70vh]">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                  <tr><th className="text-left py-2">Fecha</th><th className="text-left">Entidad</th><th className="text-left">Acción</th><th className="text-left">Usuario</th><th className="text-left">Detalle</th></tr>
                </thead>
                <tbody>
                  {data.map((l, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-2 whitespace-nowrap text-xs">{l.ts ? new Date(l.ts).toLocaleString("es-CO") : "—"}</td>
                      <td>{l.entidad} <span className="text-slate-400">{l.entidad_id}</span></td>
                      <td>{l.accion}</td>
                      <td>{l.usuario_id ?? "—"}</td>
                      <td className="max-w-[420px] truncate text-slate-500" title={l.valor_despues ?? ""}>{l.valor_despues}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </DataState>
    </div>
  );
}
