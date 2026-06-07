import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import "./index.css";
import Login from "./pages/Login";
import Layout from "./pages/Layout";
import Dashboard from "./pages/Dashboard";
import Comparativa from "./pages/Comparativa";
import Resumen from "./pages/Resumen";
import Terceros from "./pages/Terceros";
import Excepciones from "./pages/Excepciones";
import Auditoria from "./pages/Auditoria";
import Config from "./pages/Config";
import Ingesta from "./pages/Ingesta";
import Usuarios from "./pages/Usuarios";

function requireAuth(element: React.ReactNode) {
  return localStorage.getItem("token") ? element : <Navigate to="/login" replace />;
}

const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  {
    path: "/",
    element: requireAuth(<Layout />),
    children: [
      { index: true, element: <Dashboard /> },
      { path: "comparativa", element: <Comparativa /> },
      { path: "resumen", element: <Resumen /> },
      { path: "terceros", element: <Terceros /> },
      { path: "excepciones", element: <Excepciones /> },
      { path: "ingesta", element: <Ingesta /> },
      { path: "auditoria", element: <Auditoria /> },
      { path: "usuarios", element: <Usuarios /> },
      { path: "config", element: <Config /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
