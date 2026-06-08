import { useMemo } from "react";
import type { ColDef } from "ag-grid-community";
import { descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { fmtCOP, fmtPct, periodoLabel } from "../lib/format";
import { PageHeader, Card, DataState } from "../components/ui";
import DataGrid from "../components/DataGrid";

interface Exc { grupo: string; tipo: string; periodo: string; total_co: number; total_es: number; diferencia: number; pct: number; causa: string | null }

export default function Excepciones() {
  const { data, loading, error, reload } = useFetch<Exc[]>("/api/excepciones");
  const empty = !!data && data.length === 0;

  const cols = useMemo<ColDef[]>(() => [
    { field: "grupo", headerName: "Grupo", pinned: "left", minWidth: 220, tooltipField: "grupo" },
    { field: "tipo", headerName: "Tipo", width: 110 },
    { field: "periodo", headerName: "Periodo", width: 120, valueFormatter: (p) => periodoLabel(p.value) },
    { field: "total_co", headerName: "Saldo CO", type: "numericColumn", valueFormatter: (p) => fmtCOP(p.value) },
    { field: "total_es", headerName: "Saldo ES", type: "numericColumn", valueFormatter: (p) => fmtCOP(p.value) },
    { field: "diferencia", headerName: "Diferencia", type: "numericColumn", valueFormatter: (p) => fmtCOP(p.value),
      cellStyle: (p) => ({ color: Math.abs(p.value) < 1000 ? "#059669" : "#dc2626", fontWeight: 600 }) },
    { field: "pct", headerName: "%", type: "numericColumn", width: 110, valueFormatter: (p) => fmtPct(p.value) },
    { field: "causa", headerName: "Causa", width: 150 },
  ], []);

  return (
    <div>
      <PageHeader title="Excepciones" subtitle="Diferencias que superan la tolerancia, ordenadas por magnitud"
        action={<button onClick={() => descargarArchivo("/api/excepciones/export", "excepciones.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">⬇️ Excel</button>} />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && <Card><DataGrid gridId="excepciones" columnDefs={cols} rowData={data} /></Card>}
      </DataState>
    </div>
  );
}
