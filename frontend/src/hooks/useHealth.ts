import { useState, useEffect, useCallback } from "react";
import { getHealth, getRagHealth } from "../api/endpoints";

export interface HealthState {
  api: boolean;
  rag: boolean;
}

export const useHealth = () => {
  const [data, setData] = useState<HealthState>({ api: false, rag: false });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchHealth = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData({ api: true, rag: true });
      } else {
        const [apiRes, ragRes] = await Promise.allSettled([
          getHealth(signal),
          getRagHealth(signal),
        ]);
        if (signal?.aborted) return;
        
        setData({
          api: apiRes.status === "fulfilled",
          rag: ragRes.status === "fulfilled",
        });
      }
    } catch (err) {
      if (signal?.aborted) return;
      setError(err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal);
    return () => controller.abort();
  }, [fetchHealth]);

  const refetch = () => fetchHealth();

  return { data, loading, error, refetch };
};
