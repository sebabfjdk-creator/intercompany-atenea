import { useMemo, useState } from "react";
import { descargarArchivo } from "../api";
import { useFetch } from "../lib/useFetch";
import { PageHeader, Card, DataState, Kpi } from "../components/ui";

interface Tercero { cuenta_es: string; nombre_fiscal: string; nif_normalizado: string; nit_colombia: string; tipo: string }
interface Resp { items: Tercero[]; kpis: { total: number; clientes: number; proveedores: number } }

export default function Terceros() {
  const { data, loading, error, reload } = useFetch<Resp>("/api/terceros");
  const [q, setQ] = useState("");
  const [tipo, setTipo] = useState("");
  const empty = !!data && data.items.length === 0;

  const filtered = useMemo(() => {
    if (!data) return [];
    const ql = q.toLowerCase();
    return data.items.filter(
      (t) =>
        (!tipo || t.tipo.toLowerCase().startsWith(tipo)) &&
        (!ql || t.nombre_fiscal.toLowerCase().includes(ql) || t.nit_colombia.includes(ql) || t.cuenta_es.includes(ql)),
    );
  }, [data, q, tipo]);

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
            <Card>
              <div className="flex gap-3 mb-4">
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar nombre, NIT o cuenta…"
                  className="border rounded px-3 py-2 text-sm flex-1" />
                <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="border rounded px-3 py-2 text-sm">
                  <option value="">Todos</option>
                  <option value="cliente">Clientes</option>
                  <option value="proveedor">Proveedores</option>
                </select>
              </div>
              <div className="overflow-x-auto max-h-[60vh]">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-slate-400 sticky top-0 bg-white">
                    <tr><th className="text-left py-2">Cuenta ES</th><th className="text-left">Nombre fiscal</th><th className="text-left">NIF norm.</th><th className="text-left">NIT Colombia</th><th className="text-left">Tipo</th></tr>
                  </thead>
                  <tbody>
                    {filtered.slice(0, 300).map((t, i) => (
                      <tr key={t.cuenta_es + i} className="border-t border-slate-100">
                        <td className="py-1.5 font-mono text-xs">{t.cuenta_es}</td>
                        <td className="truncate max-w-[280px]" title={t.nombre_fiscal}>{t.nombre_fiscal}</td>
                        <td className="font-mono text-xs">{t.nif_normalizado}</td>
                        <td className="font-mono text-xs">{t.nit_colombia}</td>
                        <td>{t.tipo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-400 mt-2">{filtered.length} resultados {filtered.length > 300 && "(mostrando 300)"}</p>
            </Card>
          </>
        )}
      </DataState>
    </div>
  );
}
