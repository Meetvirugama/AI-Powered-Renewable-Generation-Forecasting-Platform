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

  // Only hand back a result for the plant and date actually requested. The
  // previous plant's response otherwise stays in state while the new request is
  // in flight, so every page rendered the old plant's action cards and battery
  // figures under the new plant's name -- and the Risk page priced the new plant
  // against the old plant's schedule. Mock mode serves one fixture for every
  // plant, so it is exempt.
  const current =
    data &&
    (import.meta.env.VITE_USE_MOCKS === "true" ||
      (data.plant_id === body.plant_id && (!body.date || data.date === body.date)))
      ? data
      : null;

  return { data: current, loading, error, refetch };
};
