import axios from "axios";

const PROD_API = "https://intercompany-atenea-production.up.railway.app";
const baseURL = import.meta.env.VITE_API_URL ?? PROD_API;

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      if (location.pathname !== "/login") location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export const API_BASE = baseURL;

// Descarga un archivo de un endpoint protegido (envía el Bearer token).
export async function descargarArchivo(url: string, filename: string) {
  const r = await api.get(url, { responseType: "blob" });
  const blobUrl = URL.createObjectURL(r.data as Blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
}
