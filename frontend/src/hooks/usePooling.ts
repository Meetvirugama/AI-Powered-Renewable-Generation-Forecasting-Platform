import { useState, useEffect, useCallback } from "react";
import { postPooling } from "../api/endpoints";
import { PoolingResponse, PoolingRequest } from "../types/api";
import dashboardMock from "../mocks/dashboard.json";

/** `enabled: false` skips the fetch — for callers that don't yet know pool_id. */
export const usePooling = (body: PoolingRequest, enabled: boolean = true) => {
  const [data, setData] = useState<PoolingResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<unknown>(null);

  const fetchPooling = useCallback(async (signal?: AbortSignal) => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData(dashboardMock.pooling_benefit as PoolingResponse);
      } else {
        const response = await postPooling(body, signal);
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
  [JSON.stringify(body), enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    fetchPooling(controller.signal);
    return () => controller.abort();
  }, [fetchPooling, enabled]);

  const refetch = () => fetchPooling();

  return { data, loading, error, refetch };
};
