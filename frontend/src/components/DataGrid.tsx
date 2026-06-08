import { useCallback, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridApi, GridReadyEvent } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

export interface DataGridProps {
  gridId: string;                 // clave de persistencia (orden/ancho/visibilidad por usuario)
  columnDefs: ColDef[];
  rowData: any[];
  height?: number | string;
  pageSize?: number;
  onRowClicked?: (data: any) => void;
  getRowClass?: (params: any) => string | undefined;
  context?: any;                  // expuesto a cellRenderers (p.ej. handlers de acciones)
}

// Grilla enterprise reutilizable (AG Grid Community, tema Quartz).
// Cubre: resize, reorder (DnD), freeze/pin (colDef.pinned), virtual scroll,
// sort, filtros por columna (floating), búsqueda rápida, columnas ocultables,
// tooltips, header sticky y persistencia por usuario en localStorage.
export default function DataGrid({ gridId, columnDefs, rowData, height = "70vh", pageSize = 50, onRowClicked, getRowClass, context }: DataGridProps) {
  const apiRef = useRef<GridApi | null>(null);
  const [search, setSearch] = useState("");
  const [colsOpen, setColsOpen] = useState(false);
  const [, force] = useState(0);
  const storeKey = `grid:${gridId}:${localStorage.getItem("rol") ?? "u"}`;

  const defaultColDef = useMemo<ColDef>(() => ({
    resizable: true, sortable: true, filter: true, floatingFilter: true,
    minWidth: 90, tooltipValueGetter: (p: any) => (p.value == null ? "" : String(p.value)),
  }), []);

  const saveState = useCallback(() => {
    if (apiRef.current) {
      try { localStorage.setItem(storeKey, JSON.stringify(apiRef.current.getColumnState())); } catch { /* noop */ }
    }
  }, [storeKey]);

  const onGridReady = useCallback((e: GridReadyEvent) => {
    apiRef.current = e.api;
    try {
      const saved = localStorage.getItem(storeKey);
      if (saved) e.api.applyColumnState({ state: JSON.parse(saved), applyOrder: true });
      else e.api.sizeColumnsToFit();
    } catch { e.api.sizeColumnsToFit(); }
    force((n) => n + 1); // re-render para poblar el selector de columnas
  }, [storeKey]);

  function reset() {
    localStorage.removeItem(storeKey);
    apiRef.current?.resetColumnState();
    apiRef.current?.sizeColumnsToFit();
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar…"
          className="border rounded px-3 py-1.5 text-sm w-64" />
        <div className="relative">
          <button onClick={() => setColsOpen((o) => !o)} className="px-3 py-1.5 text-sm border rounded text-slate-600">Columnas ▾</button>
          {colsOpen && apiRef.current && (
            <div className="absolute z-30 mt-1 bg-white border border-slate-200 rounded shadow-lg p-2 max-h-72 overflow-auto text-sm w-56">
              {apiRef.current.getColumns()?.map((col) => (
                <label key={col.getColId()} className="flex items-center gap-2 px-1 py-0.5 hover:bg-slate-50 rounded">
                  <input type="checkbox" defaultChecked={col.isVisible()}
                    onChange={(ev) => { apiRef.current?.setColumnVisible(col.getColId(), ev.target.checked); saveState(); }} />
                  <span className="truncate">{col.getColDef().headerName ?? col.getColId()}</span>
                </label>
              ))}
            </div>
          )}
        </div>
        <button onClick={reset} className="px-3 py-1.5 text-sm border rounded text-slate-500 ml-auto" title="Restablecer orden/ancho/columnas">Restablecer vista</button>
      </div>
      <div className="ag-theme-quartz" style={{ height, width: "100%" }}>
        <AgGridReact
          columnDefs={columnDefs}
          rowData={rowData}
          defaultColDef={defaultColDef}
          quickFilterText={search}
          context={context}
          animateRows
          enableCellTextSelection
          suppressDragLeaveHidesColumns
          tooltipShowDelay={300}
          pagination
          paginationPageSize={pageSize}
          rowHeight={34}
          headerHeight={40}
          onGridReady={onGridReady}
          onColumnMoved={saveState}
          onColumnResized={saveState}
          onColumnVisible={saveState}
          onColumnPinned={saveState}
          onSortChanged={saveState}
          onRowClicked={(e) => onRowClicked?.(e.data)}
          getRowClass={getRowClass}
        />
      </div>
    </div>
  );
}
