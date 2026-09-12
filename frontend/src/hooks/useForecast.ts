import { useState, useEffect, useCallback } from "react";
import { getForecast } from "../api/endpoints";
import { ForecastResponse } from "../types/api";
import dashboardMock from "../mocks/dashboard.json";

export type Horizon = 24 | 48 | 72;

/**
 * GET /forecast at a chosen horizon.
 *
 * The dashboard route is fixed at one settlement day, so anything past 24 hours
 * has to come from here. Each horizon is served by the booster trained for that
 * lead time on the backend -- the response's `model_name` says which.
 */
export const useForecast = (plantId: string, date: string | undefined, hours: Horizon) => {
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchForecast = useCallback(
    async (signal?: AbortSignal) => {
      if (!plantId) return;
      setLoading(true);
      setError(null);
      // Clear the previous horizon's blocks so the chart never draws 96 blocks
      // under a "72 hours" label while the longer request is in flight.
      setData(null);
      try {
        if (import.meta.env.VITE_USE_MOCKS === "true") {
          // The mock fixture holds one day only. It is returned as-is rather
          // than repeated, so an offline demo shows 96 blocks honestly instead
          // of a fabricated three-day series.
          setData((dashboardMock as { forecast: ForecastResponse }).forecast);
        } else {
          const response = await getForecast(plantId, date, hours, signal);
          if (signal?.aborted) return;
          setData(response);
        }
      } catch (err) {
        if (signal?.aborted) return;
        setError(err);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [plantId, date, hours],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchForecast(controller.signal);
    return () => controller.abort();
  }, [fetchForecast]);

  const refetch = () => fetchForecast();

  return { data, loading, error, refetch };
};
