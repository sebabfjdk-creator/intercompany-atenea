import { useState } from "react";
import { api } from "../api";
import { useFetch } from "../lib/useFetch";
import { PageHeader, Card, DataState } from "../components/ui";

interface Me { id: number; email: string; nombre: string; rol: string }
interface U { id: number; email: string; nombre: string; rol: string; activo: boolean }

function MiPassword({ myId }: { myId: number }) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      await api.patch(`/api/users/${myId}/password`, { actual, nueva });
      setMsg({ ok: true, t: "Contraseña actualizada" }); setActual(""); setNueva("");
    } catch (err: any) {
      setMsg({ ok: false, t: err?.response?.data?.detail ?? "Error" });
    }
  }
  return (
    <Card title="Cambiar mi contraseña">
      <form onSubmit={submit} className="flex flex-wrap gap-3 items-end">
        <div><label className="text-xs text-slate-500 block">Actual</label>
          <input type="password" value={actual} onChange={(e) => setActual(e.target.value)} className="border rounded px-3 py-2 text-sm" required /></div>
        <div><label className="text-xs text-slate-500 block">Nueva</label>
          <input type="password" value={nueva} onChange={(e) => setNueva(e.target.value)} className="border rounded px-3 py-2 text-sm" required minLength={4} /></div>
        <button className="px-3 py-2 bg-co text-white rounded text-sm">Actualizar</button>
        {msg && <span className={`text-sm ${msg.ok ? "text-emerald-600" : "text-red-600"}`}>{msg.t}</span>}
      </form>
    </Card>
  );
}

function CrearUsuario({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ email: "", nombre: "", password: "", rol: "admin_co" });
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      await api.post("/api/users", f);
      setMsg({ ok: true, t: "Usuario creado" }); setF({ email: "", nombre: "", password: "", rol: "admin_co" }); onDone();
    } catch (err: any) { setMsg({ ok: false, t: err?.response?.data?.detail ?? "Error" }); }
  }
  return (
    <Card title="Crear usuario">
      <form onSubmit={submit} className="grid md:grid-cols-5 gap-3 items-end">
        <div><label className="text-xs text-slate-500 block">Email</label>
          <input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} className="border rounded px-3 py-2 text-sm w-full" required /></div>
        <div><label className="text-xs text-slate-500 block">Nombre</label>
          <input value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} className="border rounded px-3 py-2 text-sm w-full" required /></div>
        <div><label className="text-xs text-slate-500 block">Contraseña</label>
          <input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} className="border rounded px-3 py-2 text-sm w-full" required minLength={4} /></div>
        <div><label className="text-xs text-slate-500 block">Rol</label>
          <select value={f.rol} onChange={(e) => setF({ ...f, rol: e.target.value })} className="border rounded px-3 py-2 text-sm w-full">
            <option value="admin_co">admin_co</option><option value="admin">admin</option>
          </select></div>
        <button className="px-3 py-2 bg-co text-white rounded text-sm">Crear</button>
      </form>
      {msg && <p className={`text-sm mt-2 ${msg.ok ? "text-emerald-600" : "text-red-600"}`}>{msg.t}</p>}
    </Card>
  );
}

export default function Usuarios() {
  const me = useFetch<Me>("/api/auth/me");
  const esAdmin = me.data?.rol === "admin";
  const users = useFetch<U[]>(esAdmin ? "/api/users" : null);

  async function resetPwd(u: U) {
    const nueva = prompt(`Nueva contraseña para ${u.email}:`);
    if (!nueva) return;
    try { await api.patch(`/api/users/${u.id}/password`, { nueva }); alert("Contraseña actualizada"); }
    catch (e: any) { alert(e?.response?.data?.detail ?? "Error"); }
  }
  async function toggle(u: U) {
    try { await api.patch(`/api/users/${u.id}/activo?activo=${!u.activo}`); users.reload(); }
    catch (e: any) { alert(e?.response?.data?.detail ?? "Error"); }
  }

  return (
    <div>
      <PageHeader title="Usuarios" subtitle="Gestión de cuentas y contraseñas" />
      <DataState loading={me.loading} error={me.error} onRetry={me.reload}>
        {me.data && (
          <div className="space-y-4">
            <MiPassword myId={me.data.id} />
            {esAdmin && <CrearUsuario onDone={users.reload} />}
            {esAdmin && (
              <Card title="Usuarios">
                <DataState loading={users.loading} error={users.error} onRetry={users.reload}>
                  <table className="w-full text-sm">
                    <thead className="text-xs uppercase text-slate-400">
                      <tr><th className="text-left py-2">Email</th><th className="text-left">Nombre</th><th className="text-left">Rol</th><th className="text-left">Estado</th><th className="text-right">Acciones</th></tr>
                    </thead>
                    <tbody>
                      {(users.data ?? []).map((u) => (
                        <tr key={u.id} className="border-t border-slate-100">
                          <td className="py-2">{u.email}</td>
                          <td>{u.nombre}</td>
                          <td><span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100">{u.rol}</span></td>
                          <td>{u.activo ? <span className="text-emerald-600">activo</span> : <span className="text-slate-400">inactivo</span>}</td>
                          <td className="text-right space-x-3">
                            <button onClick={() => resetPwd(u)} className="text-co text-xs hover:underline">Reset contraseña</button>
                            {u.id !== me.data!.id && <button onClick={() => toggle(u)} className="text-xs text-slate-500 hover:underline">{u.activo ? "Desactivar" : "Activar"}</button>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </DataState>
              </Card>
            )}
          </div>
        )}
      </DataState>
    </div>
  );
}
