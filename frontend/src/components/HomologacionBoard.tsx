import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
  useDraggable, useDroppable, type DragEndEvent, type DragStartEvent,
} from "@dnd-kit/core";
import { api } from "../api";

export interface Grupo {
  id?: number | null; grupo: string; tipo: string; tipo_relacion: string;
  cuentas_co: string[]; cuentas_es: string[];
}

type Pais = "CO" | "ES";
interface Move { cuenta: string; pais: Pais; origen: string; destino: string }

const enc = (...p: string[]) => p.join("::");
const dec = (s: string) => s.split("::");

// Aplica un movimiento sobre el estado local (optimista).
function applyMove(grupos: Grupo[], m: Move): Grupo[] {
  const key = m.pais === "CO" ? "cuentas_co" : "cuentas_es";
  return grupos.map((g) => {
    if (g.grupo === m.origen) return { ...g, [key]: (g as any)[key].filter((c: string) => c !== m.cuenta) };
    if (g.grupo === m.destino) return { ...g, [key]: [...new Set([...(g as any)[key], m.cuenta])].sort() };
    return g;
  });
}

function Chip({ pais, cuenta, grupo, disabled }: { pais: Pais; cuenta: string; grupo: string; disabled: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: enc("chip", pais, cuenta, grupo), disabled,
  });
  const color = pais === "CO" ? "border-co/40 text-co" : "border-es/40 text-es";
  return (
    <span ref={setNodeRef} {...listeners} {...attributes}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border bg-white text-xs font-mono select-none
        ${color} ${disabled ? "cursor-default" : "cursor-grab active:cursor-grabbing hover:shadow-sm"}
        ${isDragging ? "opacity-30" : ""}`}
      title={disabled ? cuenta : `Arrastra ${cuenta} a otro grupo`}>
      {!disabled && <span className="text-slate-300 leading-none">⋮⋮</span>}{cuenta}
    </span>
  );
}

function Zone({ pais, grupo, overPais, children }: { pais: Pais; grupo: string; overPais: Pais | null; children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: enc("zone", pais, grupo) });
  const valido = isOver && overPais === pais;       // resaltar solo si el país coincide
  const invalido = isOver && overPais !== null && overPais !== pais;
  const ring = valido ? "ring-2 ring-emerald-400 bg-emerald-50/50"
    : invalido ? "ring-2 ring-red-300 bg-red-50/40" : "";
  return (
    <div ref={setNodeRef} className={`rounded-md border border-dashed border-slate-200 p-2 min-h-[40px] transition ${ring}`}>
      <div className={`text-[10px] font-semibold uppercase mb-1 ${pais === "CO" ? "text-co" : "text-es"}`}>{pais === "CO" ? "Colombia" : "España"}</div>
      <div className="flex flex-wrap gap-1">{children}</div>
    </div>
  );
}

export default function HomologacionBoard({ grupos, puedeEditar, onChanged }:
  { grupos: Grupo[]; puedeEditar: boolean; onChanged?: () => void }) {
  const [board, setBoard] = useState<Grupo[]>(grupos);
  const [active, setActive] = useState<{ pais: Pais; cuenta: string } | null>(null);
  const [toast, setToast] = useState("");
  const [undo, setUndo] = useState<Move | null>(null);
  const [q, setQ] = useState("");
  const undoTimer = useRef<number | null>(null);

  useEffect(() => { setBoard(grupos); }, [grupos]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  function flashToast(t: string) { setToast(t); window.setTimeout(() => setToast(""), 3500); }

  function armUndo(m: Move) {
    setUndo(m);
    if (undoTimer.current) window.clearTimeout(undoTimer.current);
    undoTimer.current = window.setTimeout(() => setUndo(null), 30000);
  }

  async function doMove(m: Move, esUndo = false) {
    const prev = board;
    setBoard((b) => applyMove(b, m));        // optimista
    try {
      const { data } = await api.post("/api/config/homologacion/mover", {
        cuenta: m.cuenta, pais: m.pais, grupo_origen: m.origen, grupo_destino: m.destino,
      });
      setBoard(data.grupos);                 // autoritativo
      if (esUndo) { flashToast("↩️ Movimiento deshecho"); setUndo(null); }
      else { flashToast(`✅ Homologación actualizada — ${m.cuenta} → ${m.destino}`); armUndo(m); }
      onChanged?.();
    } catch (e: any) {
      setBoard(prev);                        // revertir
      window.alert(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "No se pudo mover la cuenta");
    }
  }

  function onDragStart(e: DragStartEvent) {
    const [, pais, cuenta] = dec(String(e.active.id));
    setActive({ pais: pais as Pais, cuenta });
  }
  function onDragEnd(e: DragEndEvent) {
    setActive(null);
    const { active: a, over } = e;
    if (!over) return;
    const [, pais, cuenta, origen] = dec(String(a.id));
    const [, zpais, destino] = dec(String(over.id));
    if (pais !== zpais) { flashToast("Solo puedes soltar en la columna del mismo país"); return; }
    if (origen === destino) return;
    doMove({ cuenta, pais: pais as Pais, origen, destino });
  }

  const ql = q.toLowerCase();
  const visibles = board.filter((g) => !ql || g.grupo.toLowerCase().includes(ql)
    || g.cuentas_co.join(",").includes(ql) || g.cuentas_es.join(",").includes(ql));

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar grupo o código…"
          className="border rounded px-3 py-2 text-sm flex-1" />
        <span className="text-xs text-slate-400">{board.length} grupos · arrastra un chip a otro grupo</span>
      </div>
      {!puedeEditar && <p className="text-xs text-amber-600 mb-3">Solo lectura: tu rol no puede mover cuentas.</p>}

      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3 max-h-[64vh] overflow-auto pr-1">
          {visibles.map((g) => (
            <div key={g.grupo} className="border border-slate-200 rounded-lg bg-white p-3 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-slate-700 text-sm truncate" title={g.grupo}>{g.grupo}</span>
                <span className="text-[10px] uppercase text-slate-400">{g.tipo}</span>
              </div>
              <div className="space-y-2">
                <Zone pais="CO" grupo={g.grupo} overPais={active?.pais ?? null}>
                  {g.cuentas_co.map((c) => <Chip key={`CO-${c}`} pais="CO" cuenta={c} grupo={g.grupo} disabled={!puedeEditar} />)}
                </Zone>
                <Zone pais="ES" grupo={g.grupo} overPais={active?.pais ?? null}>
                  {g.cuentas_es.map((c) => <Chip key={`ES-${c}`} pais="ES" cuenta={c} grupo={g.grupo} disabled={!puedeEditar} />)}
                </Zone>
              </div>
            </div>
          ))}
        </div>
        <DragOverlay>
          {active && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border bg-white text-xs font-mono shadow-lg">
              {active.cuenta}
            </span>
          )}
        </DragOverlay>
      </DndContext>

      {active && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-xs px-3 py-1.5 rounded-full shadow-lg z-40">
          Moviendo cuenta {active.cuenta} ({active.pais})
        </div>
      )}
      {toast && (
        <div className="fixed bottom-4 right-4 bg-emerald-600 text-white text-sm px-4 py-2 rounded-lg shadow-lg z-40 flex items-center gap-3">
          {toast}
          {undo && (
            <button onClick={() => doMove({ ...undo, origen: undo.destino, destino: undo.origen }, true)}
              className="underline font-medium">Deshacer</button>
          )}
        </div>
      )}
    </div>
  );
}
