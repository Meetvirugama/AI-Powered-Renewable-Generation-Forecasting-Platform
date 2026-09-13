import { useState, useEffect, useCallback } from "react";
import { postDsm } from "../api/endpoints";
import { DSMResponse, DSMRequest } from "../types/api";
import dashboardMock from "../mocks/dashboard.json";

/**
 * `enabled: false` skips the fetch entirely. Callers building `body.schedule_mw` from
 * another in-flight request (the optimiser) should stay disabled until that schedule
 * is real — otherwise this fires once with `schedule_mw: []` before firing again with
 * the real schedule, wasting a request and briefly showing an all-zero heatmap.
 */
export const useDSM = (body: DSMRequest, enabled: boolean = true) => {
  const [data, setData] = useState<DSMResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<unknown>(null);

  const fetchDsm = useCallback(async (signal?: AbortSignal) => {
    if (!enabled) return;
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
  [JSON.stringify(body), enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    fetchDsm(controller.signal);
    return () => controller.abort();
  }, [fetchDsm, enabled]);

  const refetch = () => fetchDsm();

  // Only return a result for the plant and date requested. When a plant change
  // disables this hook until the new schedule arrives, the old plant's heatmap
  // would otherwise remain in state and be shown under the new plant's name.
  const current =
    data &&
    (import.meta.env.VITE_USE_MOCKS === "true" ||
      (data.plant_id === body.plant_id && (!body.date || data.date === body.date)))
      ? data
      : null;

  return { data: current, loading, error, refetch };
};
