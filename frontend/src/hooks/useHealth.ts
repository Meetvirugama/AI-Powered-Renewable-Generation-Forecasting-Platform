import { useState, useEffect, useCallback } from "react";
import { getHealth, getRagHealth } from "../api/endpoints";

export interface HealthState {
  api: boolean;
  rag: boolean;
  /** Names of modules serving synthetic / mock data. From GET /health .serving_synthetic_data */
  syntheticModules: string[];
  /** Per-engine type strings. From GET /health .engines */
  engines: Record<string, string>;
}

export const useHealth = () => {
  const [data, setData] = useState<HealthState>({
    api: false,
    rag: false,
    syntheticModules: [],
    engines: {},
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchHealth = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData({ api: true, rag: true, syntheticModules: ["forecast"], engines: { forecast: "mock" } });
      } else {
        const [apiRes, ragRes] = await Promise.allSettled([
          getHealth(),
          getRagHealth(),
        ]);
        if (signal?.aborted) return;

        const apiOk = apiRes.status === "fulfilled";
        const raw = apiOk ? (apiRes.value as Record<string, unknown>) : {};

        setData({
          api: apiOk,
          rag: ragRes.status === "fulfilled",
          syntheticModules: Array.isArray(raw.serving_synthetic_data)
            ? (raw.serving_synthetic_data as string[])
            : [],
          engines: (raw.engines as Record<string, string>) ?? {},
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
