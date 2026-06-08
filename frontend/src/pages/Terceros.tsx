import { useMemo } from "react";
import type { ColDef } from "ag-grid-community";
import { descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";
import DataGrid from "../components/DataGrid";

interface Tercero { cuenta_es: string; nombre_fiscal: string; nif_normalizado: string; nit_colombia: string; tipo: string }
interface Resp { items: Tercero[]; kpis: { total: number; clientes: number; proveedores: number } }

export default function Terceros() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/terceros");
  const empty = !!data && data.items.length === 0;

  const cols = useMemo<ColDef[]>(() => [
    { field: "cuenta_es", headerName: "Cuenta ES", width: 140, pinned: "left" },
    { field: "nombre_fiscal", headerName: "Nombre fiscal", minWidth: 280, tooltipField: "nombre_fiscal" },
    { field: "nif_normalizado", headerName: "NIF norm.", width: 150 },
    { field: "nit_colombia", headerName: "NIT Colombia", width: 150 },
    { field: "tipo", headerName: "Tipo", width: 130 },
  ], []);

  return (
    <div>
      <PageHeader title="Terceros (AR/AP)" subtitle="Puente NIF (España) ↔ NIT (Colombia)"
        action={<button onClick={() => descargarArchivo("/api/terceros/export", "terceros.xlsx")} className="px-3 py-1.5 text-sm border rounded text-slate-600">⬇️ Excel</button>} />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && (
          <>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <Kpi label="Total terceros" value={data.kpis.total} tone="blue" />
              <Kpi label="Clientes" value={data.kpis.clientes} tone="green" />
              <Kpi label="Proveedores" value={data.kpis.proveedores} tone="amber" />
            </div>
            <Card><DataGrid gridId="terceros" columnDefs={cols} rowData={data.items} pageSize={100} /></Card>
          </>
        )}
      </DataState>
    </div>
  );
}
