import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

export function useFetch<T>(url: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!url) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<T>(url);
      setData(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Error de red");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, loading, error, reload };
}

export const rol = () => localStorage.getItem("rol") ?? "";
export const esAdmin = () => rol() === "admin";
