import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

const TOP = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/comparativa", label: "Comparativa" },
  { to: "/resumen", label: "Resumen" },
  { to: "/excepciones", label: "Excepciones" },
  { to: "/anomalias", label: "Anomalías" },
  { to: "/ar-ap", label: "AR/AP" },
  { to: "/cartera", label: "Cartera 360°" },
];

// Submenú "Configuración" — centraliza la parametrización del sistema.
const CONFIG_SUB = [
  { to: "/config", label: "Homologación de cuentas", end: true },
  { to: "/terceros", label: "Terceros" },
  { to: "/ingesta", label: "Ingesta" },
  { to: "/usuarios", label: "Usuarios" },
  { to: "/config/parametros", label: "Parámetros generales" },
  { to: "/auditoria", label: "Auditoría" },
];

const linkCls = ({ isActive }: { isActive: boolean }) =>
  `block px-3 py-2 rounded text-sm ${isActive ? "bg-co font-medium text-white" : "hover:bg-slate-700/60 text-slate-300"}`;

export default function Layout() {
  const nav = useNavigate();
  const { pathname } = useLocation();
  const nombre = localStorage.getItem("nombre") ?? "";
  const rol = localStorage.getItem("rol") ?? "";

  const inConfig = CONFIG_SUB.some((s) => pathname === s.to || pathname.startsWith(s.to + "/"));
  const [openConfig, setOpenConfig] = useState(inConfig);
  // Auto-expandir el acordeón cuando navegas a una de sus secciones
  useEffect(() => { if (inConfig) setOpenConfig(true); }, [inConfig]);

  function logout() { localStorage.clear(); nav("/login"); }

  return (
    <div className="min-h-screen flex bg-slate-50">
      <aside className="w-60 bg-slate-900 text-slate-100 flex flex-col">
        <div className="px-5 py-4 border-b border-slate-700">
          <div className="font-bold text-lg leading-tight">Atenea IC</div>
          <div className="text-[11px] text-slate-400">Colombia ↔ España</div>
        </div>
        <nav className="p-3 space-y-1 flex-1 overflow-y-auto">
          {TOP.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={linkCls}>{n.label}</NavLink>
          ))}

          {/* Acordeón Configuración */}
          <div className="pt-1">
            <button
              onClick={() => setOpenConfig((o) => !o)}
              aria-expanded={openConfig}
              className={`w-full flex items-center justify-between px-3 py-2 rounded text-sm ${inConfig ? "text-white" : "text-slate-300"} hover:bg-slate-700/60`}
            >
              <span>Configuración</span>
              <span className={`text-xs transition-transform duration-200 ${openConfig ? "rotate-180" : ""}`}>▼</span>
            </button>
            {openConfig && (
              <div className="mt-1 ml-2 pl-2 border-l border-slate-700 space-y-1">
                {CONFIG_SUB.map((s) => (
                  <NavLink key={s.to} to={s.to} end={s.end} className={linkCls}>{s.label}</NavLink>
                ))}
              </div>
            )}
          </div>
        </nav>
        <div className="p-3 text-[11px] text-slate-500 border-t border-slate-700">v0.5 · MVP</div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-6 py-3 flex justify-between items-center">
          <span className="text-sm text-slate-500">
            {nombre} · <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100">{rol}</span>
            {rol === "admin_co" && <span className="ml-2 text-xs text-amber-600">(España: solo lectura)</span>}
          </span>
          <button onClick={logout} className="text-sm text-red-600 hover:underline">Salir</button>
        </header>
        <main className="p-6 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
