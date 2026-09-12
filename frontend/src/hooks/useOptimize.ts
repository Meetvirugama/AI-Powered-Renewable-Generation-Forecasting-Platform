import { useState, useEffect, useCallback } from "react";
import { postOptimize } from "../api/endpoints";
import { OptimizeResponse, OptimizeRequest } from "../types/api";
// GET /dashboard does not carry the optimiser payload — POST /optimize is a separate
// call, so it gets its own fixture rather than a fabricated key on the dashboard mock.
import optimizeMock from "../mocks/optimize.json";

export const useOptimize = (body: OptimizeRequest) => {
  const [data, setData] = useState<OptimizeResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchOptimize = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData(optimizeMock as OptimizeResponse);
      } else {
        const response = await postOptimize(body, signal);
        if (signal?.aborted) return;
        setData(response);
      }
    } catch (err) {
      if (signal?.aborted) return;
      setError(err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, /* eslint-disable-next-line react-hooks/exhaustive-deps */
  [JSON.stringify(body)]);

  useEffect(() => {
    const controller = new AbortController();
    fetchOptimize(controller.signal);
    return () => controller.abort();
  }, [fetchOptimize]);

  const refetch = () => fetchOptimize();

  return { data, loading, error, refetch };
};
