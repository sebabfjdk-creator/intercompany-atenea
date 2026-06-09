import { useMemo } from "react";
import type { ColDef } from "ag-grid-community";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { fmtCOP } from "../lib/format";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";
import DataGrid from "../components/DataGrid";

interface Cliente {
  nit: string; nombre: string; saldo: number; saldo_430: number; saldo_431: number;
  dias: number | null; antiguedad: string; riesgo: string;
}
interface Aging { bucket: string; saldo: number; clientes: number }
interface Top { nombre: string; nit: string; saldo: number; pct: number }
interface Resp {
  kpis: {
    cartera_total: number; clientes: number; dudoso_431: number; provisional_es: number;
    monto_critico_90: number; clientes_riesgo: number; provision_recomendada: number; concentracion_top1: number;
  };
  aging: Aging[]; top10: Top[]; clientes: Cliente[]; analisis: string[]; nota: string;
}

const AGING_COLOR: Record<string, string> = {
  "0-30": "#059669", "31-60": "#65a30d", "61-90": "#d97706",
  "91-120": "#dc2626", "120+": "#7f1d1d", "Sin movimiento": "#94a3b8",
};
const RIESGO = (r: string) => ({ bajo: "🟢 Bajo", medio: "🟡 Medio", alto: "🔴 Alto", critico: "⚫ Crítico" }[r] ?? r);

export default function Cartera() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/cartera/dashboard");
  const empty = !!data && data.clientes.length === 0;

  const cols = useMemo<ColDef[]>(() => [
    { field: "nombre", headerName: "Cliente", minWidth: 240, pinned: "left", tooltipField: "nombre" },
    { field: "nit", headerName: "NIF/NIT", width: 130 },
    { field: "saldo", headerName: "Saldo", width: 150, type: "rightAligned", valueFormatter: (p: any) => fmtCOP(p.value) },
    { field: "saldo_431", headerName: "Dudoso (431)", width: 140, type: "rightAligned", valueFormatter: (p: any) => (p.value ? fmtCOP(p.value) : "—") },
    { field: "dias", headerName: "Días s/mov", width: 120, type: "rightAligned", valueFormatter: (p: any) => (p.value ?? "—") },
    { field: "antiguedad", headerName: "Antigüedad", width: 130 },
    { field: "riesgo", headerName: "Riesgo", width: 130, valueFormatter: (p: any) => RIESGO(p.value) },
  ], []);

  return (
    <div>
      <PageHeader title="Cartera 360°" subtitle="Centro ejecutivo de cobro y riesgo — clientes España (430 / 431 dudoso cobro)"
        action={data && !empty ? (
          <button onClick={() => descargarArchivo("/api/cartera/export", "cartera_360.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">📥 Exportar Excel</button>
        ) : null} />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <Kpi label="Cartera total" value={fmtCOP(data.kpis.cartera_total)} tone="blue" />
              <Kpi label="Clientes con saldo" value={data.kpis.clientes} />
              <Kpi label="Antigüedad >90 días" value={fmtCOP(data.kpis.monto_critico_90)} tone="red" hint={`${data.kpis.clientes_riesgo} clientes en riesgo`} />
              <Kpi label="Dudoso cobro (431)" value={fmtCOP(data.kpis.dudoso_431)} tone="amber" />
              <Kpi label="Provisión recomendada" value={fmtCOP(data.kpis.provision_recomendada)} tone="amber" hint="por antigüedad" />
              <Kpi label="Provisionales ES" value={fmtCOP(data.kpis.provisional_es)} hint="fact. pend. emitir (no cruzan)" />
              <Kpi label="Concentración mayor cliente" value={`${data.kpis.concentracion_top1}%`} tone={data.kpis.concentracion_top1 >= 20 ? "red" : "slate"} />
            </div>

            {data.analisis.length > 0 && (
              <Card title="🧠 Análisis automático" className="mb-4">
                <ul className="space-y-1.5 text-sm text-slate-700 list-disc pl-5">
                  {data.analisis.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              </Card>
            )}

            <div className="grid md:grid-cols-2 gap-4 mb-4">
              <Card title="Aging por antigüedad (saldo)">
                {data.aging.length === 0 ? <p className="text-sm text-slate-400">Sin saldos.</p> : (
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie data={data.aging} dataKey="saldo" nameKey="bucket" innerRadius={60} outerRadius={100} label={(e: any) => e.bucket}>
                        {data.aging.map((a) => <Cell key={a.bucket} fill={AGING_COLOR[a.bucket] ?? "#94a3b8"} />)}
                      </Pie>
                      <Tooltip formatter={(v: any) => fmtCOP(Number(v))} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </Card>
              <Card title="Concentración — Top 10 clientes">
                {data.top10.length === 0 ? <p className="text-sm text-slate-400">Sin clientes.</p> : (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={data.top10} layout="vertical" margin={{ left: 20, right: 20 }}>
                      <XAxis type="number" tickFormatter={(v) => fmtCOP(v)} hide />
                      <YAxis type="category" dataKey="nombre" width={140} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v: any) => fmtCOP(Number(v))} />
                      <Bar dataKey="saldo" fill="#1565c0" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </Card>
            </div>

            <Card title="Matriz de cobrabilidad">
              <DataGrid gridId="cartera-matriz" columnDefs={cols} rowData={data.clientes} pageSize={50} height="50vh" />
            </Card>

            <p className="text-xs text-slate-400 mt-3">{data.nota} Moneda COP. El detalle por tercero (movimientos, matching CO↔ES) está en la página <b>AR/AP</b>.</p>
          </>
        )}
      </DataState>
    </div>
  );
}
