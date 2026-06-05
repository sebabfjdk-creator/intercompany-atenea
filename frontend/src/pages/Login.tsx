import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Login() {
  const [email, setEmail] = useState("admin@atenea.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const form = new URLSearchParams({ username: email, password });
      const { data } = await api.post("/api/auth/login", form);
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("rol", data.rol);
      localStorage.setItem("nombre", data.nombre);
      nav("/comparativa");
    } catch {
      setError("Usuario o contraseña incorrectos");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <form onSubmit={submit} className="bg-white shadow rounded-lg p-8 w-96 space-y-4">
        <h1 className="text-xl font-bold">Intercompany Atenea</h1>
        <p className="text-sm text-slate-500">Conciliación Colombia ↔ España</p>
        <input
          className="w-full border rounded px-3 py-2"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="w-full border rounded px-3 py-2"
          type="password"
          placeholder="Contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button className="w-full bg-co text-white rounded py-2 font-medium">Entrar</button>
      </form>
    </div>
  );
}
