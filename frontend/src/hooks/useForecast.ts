import { useState, useEffect, useCallback } from "react";
import { getForecast } from "../api/endpoints";
import { ForecastResponse } from "../types/api";
import dashboardMock from "../mocks/dashboard.json";

export const useForecast = (plantId: string, date?: string) => {
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchForecast = useCallback(async (signal?: AbortSignal) => {
    if (!plantId) return;
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData(dashboardMock.forecast as ForecastResponse);
      } else {
        const response = await getForecast(plantId, date, signal);
        if (signal?.aborted) return;
        setData(response);
      }
    } catch (err) {
      if (signal?.aborted) return;
      setError(err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [plantId, date]);

  useEffect(() => {
    const controller = new AbortController();
    fetchForecast(controller.signal);
    return () => controller.abort();
  }, [fetchForecast]);

  const refetch = () => fetchForecast();

  return { data, loading, error, refetch };
};
