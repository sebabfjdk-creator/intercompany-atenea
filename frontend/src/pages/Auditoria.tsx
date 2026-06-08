import { useMemo } from "react";
import type { ColDef } from "ag-grid-community";
import { useFetch } from "../lib/useFetch";
import { PageHeader, Card, DataState } from "../components/ui";
import DataGrid from "../components/DataGrid";

interface Log { entidad: string; entidad_id: string; accion: string; valor_despues: string | null; usuario_id: number | null; ts: string | null }

export default function Auditoria() {
  const { data, loading, error, reload } = useFetch<Log[]>("/api/auditoria");
  const empty = !!data && data.length === 0;

  const cols = useMemo<ColDef[]>(() => [
    { field: "ts", headerName: "Fecha", width: 180, pinned: "left",
      valueFormatter: (p) => (p.value ? new Date(p.value).toLocaleString("es-CO") : "—") },
    { field: "entidad", headerName: "Entidad", width: 140 },
    { field: "entidad_id", headerName: "ID", width: 110 },
    { field: "accion", headerName: "Acción", width: 120 },
    { field: "usuario_id", headerName: "Usuario", width: 110 },
    { field: "valor_despues", headerName: "Detalle", minWidth: 320, tooltipField: "valor_despues" },
  ], []);

  return (
    <div>
      <PageHeader title="Auditoría" subtitle="Registro inmutable de cambios (quién, qué, cuándo)" />
      <DataState loading={loading} error={error} empty={empty} onRetry={reload}>
        {data && <Card><DataGrid gridId="auditoria" columnDefs={cols} rowData={data} /></Card>}
      </DataState>
    </div>
  );
}
