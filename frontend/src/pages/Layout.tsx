import { NavLink, Outlet, useNavigate } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/comparativa", label: "Comparativa" },
  { to: "/resumen", label: "Resumen" },
  { to: "/terceros", label: "Terceros (AR/AP)" },
  { to: "/excepciones", label: "Excepciones" },
  { to: "/ingesta", label: "Ingesta" },
  { to: "/auditoria", label: "Auditoría" },
  { to: "/config", label: "Configuración" },
];

export default function Layout() {
  const nav = useNavigate();
  const nombre = localStorage.getItem("nombre") ?? "";
  const rol = localStorage.getItem("rol") ?? "";

  function logout() {
    localStorage.clear();
    nav("/login");
  }

  return (
    <div className="min-h-screen flex bg-slate-50">
      <aside className="w-60 bg-slate-900 text-slate-100 flex flex-col">
        <div className="px-5 py-4 border-b border-slate-700">
          <div className="font-bold text-lg leading-tight">Atenea IC</div>
          <div className="text-[11px] text-slate-400">Colombia ↔ España</div>
        </div>
        <nav className="p-3 space-y-1 flex-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `block px-3 py-2 rounded text-sm ${isActive ? "bg-co font-medium" : "hover:bg-slate-700/60 text-slate-300"}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 text-[11px] text-slate-500 border-t border-slate-700">v0.2 · MVP</div>
      </aside>
      <div className="flex-1 flex flex-col min-w-0">
        <header className="bg-white border-b border-slate-200 px-6 py-3 flex justify-between items-center">
          <span className="text-sm text-slate-500">
            {nombre} · <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100">{rol}</span>
            {rol === "admin_co" && <span className="ml-2 text-xs text-amber-600">(España: solo lectura)</span>}
          </span>
          <button onClick={logout} className="text-sm text-red-600 hover:underline">
            Salir
          </button>
        </header>
        <main className="p-6 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
