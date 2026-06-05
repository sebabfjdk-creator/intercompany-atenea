import { NavLink, Outlet, useNavigate } from "react-router-dom";

const NAV = [
  { to: "/comparativa", label: "Comparativa" },
  { to: "/resumen", label: "Resumen" },
  { to: "/terceros", label: "Terceros (AR/AP)" },
  { to: "/excepciones", label: "Excepciones" },
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
    <div className="min-h-screen flex">
      <aside className="w-60 bg-slate-900 text-slate-100 p-4 space-y-1">
        <div className="font-bold text-lg mb-4">Atenea IC</div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `block px-3 py-2 rounded ${isActive ? "bg-co" : "hover:bg-slate-700"}`
            }
          >
            {n.label}
          </NavLink>
        ))}
      </aside>
      <div className="flex-1 flex flex-col">
        <header className="bg-white border-b px-6 py-3 flex justify-between items-center">
          <span className="text-sm text-slate-500">
            {nombre} · <span className="font-mono">{rol}</span>
          </span>
          <button onClick={logout} className="text-sm text-red-600">
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
