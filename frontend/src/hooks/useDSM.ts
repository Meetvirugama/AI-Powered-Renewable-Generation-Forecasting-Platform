import { useState, useEffect, useCallback } from "react";
import { postDsm } from "../api/endpoints";
import { DSMResponse, DSMRequest } from "../types/api";
import dashboardMock from "../mocks/dashboard.json";

export const useDSM = (body: DSMRequest) => {
  const [data, setData] = useState<DSMResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchDsm = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData(dashboardMock.dsm_summary as DSMResponse);
      } else {
        const response = await postDsm(body, signal);
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
    fetchDsm(controller.signal);
    return () => controller.abort();
  }, [fetchDsm]);

  const refetch = () => fetchDsm();

  return { data, loading, error, refetch };
};
