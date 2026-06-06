import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Kpi, Card, DataState } from "../components/ui";

interface Estado {
  colombia_cuentas: number; espana_cuentas: number; homologacion_mappings: number;
  terceros: number; periodos: string[]; listo_para_comparativa: boolean;
}
interface Comp { kpis: { grupos: number; cruces: number; conciliados: number; excepciones: number; dif_total_abs: number } }

export default function Dashboard() {
  const est = useFetch<Estado>("/api/estado-datos");
  const comp = useFetch<Comp>("/api/comparativa");

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Estado de la conciliación intercompany Colombia ↔ España" />
      <DataState loading={est.loading} error={est.error} onRetry={est.reload}>
        {!est.data?.listo_para_comparativa ? (
          <Card>
            <div className="text-center py-8">
              <p className="text-slate-600 mb-2">Aún no hay datos suficientes para conciliar.</p>
              <p className="text-slate-400 text-sm mb-4">
                Necesitas ingerir: homologación, balance Colombia y libro mayor España.
              </p>
              <Link to="/ingesta" className="inline-block px-4 py-2 bg-co text-white rounded font-medium">
                Ir a Ingesta
              </Link>
            </div>
          </Card>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <Kpi label="Grupos homologados" value={comp.data?.kpis.grupos ?? "—"} tone="blue" />
              <Kpi label="Conciliados" value={comp.data?.kpis.conciliados ?? "—"} tone="green" hint={`de ${comp.data?.kpis.cruces ?? 0} cruces`} />
              <Kpi label="Excepciones" value={comp.data?.kpis.excepciones ?? "—"} tone="red" />
              <Kpi label="Σ |Diferencias|" value={fmtCOP(comp.data?.kpis.dif_total_abs)} tone="amber" />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <Card title="Conciliación">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={[
                    { name: "Conciliados", v: comp.data?.kpis.conciliados ?? 0 },
                    { name: "Excepciones", v: comp.data?.kpis.excepciones ?? 0 },
                  ]}>
                    <XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
                    <Bar dataKey="v" radius={[6, 6, 0, 0]}>
                      <Cell fill="#059669" /><Cell fill="#dc2626" />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Datos ingeridos">
                <ul className="text-sm space-y-2">
                  <li className="flex justify-between"><span>Cuentas Colombia (balance)</span><b>{est.data?.colombia_cuentas}</b></li>
                  <li className="flex justify-between"><span>Cuentas España (libro mayor)</span><b>{est.data?.espana_cuentas}</b></li>
                  <li className="flex justify-between"><span>Mapeos de homologación</span><b>{est.data?.homologacion_mappings}</b></li>
                  <li className="flex justify-between"><span>Terceros (puente NIF↔NIT)</span><b>{est.data?.terceros}</b></li>
                  <li className="flex justify-between"><span>Periodos</span><b>{est.data?.periodos.join(", ")}</b></li>
                </ul>
              </Card>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}
