import { useState, useEffect, useCallback } from "react";
import { getPlants } from "../api/endpoints";
import { PlantsResponse } from "../types/api";
import plantsMock from "../mocks/plants.json";

export const usePlants = () => {
  const [data, setData] = useState<PlantsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchPlants = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData(plantsMock as PlantsResponse);
      } else {
        const response = await getPlants(signal);
        if (signal?.aborted) return;
        setData(response);
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
    fetchPlants(controller.signal);
    return () => controller.abort();
  }, [fetchPlants]);

  const refetch = () => fetchPlants();

  return { data, loading, error, refetch };
};
