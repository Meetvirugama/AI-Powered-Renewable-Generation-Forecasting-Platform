import { useState, useEffect, useCallback } from "react";
import { getDashboard } from "../api/endpoints";
import { DashboardResponse } from "../types/api";
import dashboardMock from "../mocks/dashboard.json";
import plantsMock from "../mocks/plants.json";

export const useDashboard = (plantId: string, date?: string) => {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchDashboard = useCallback(async (signal?: AbortSignal) => {
    if (!plantId) return;
    setLoading(true);
    setError(null);
    // Clear the previous plant's response so consumers gated on `!data` show a
    // skeleton during the refetch instead of the old plant's numbers under the
    // new plant's name.
    setData(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        // Patch the single mock fixture with the selected plant's identity
        // so the UI reflects the correct plant name/capacity when switching.
        const plant = plantsMock.plants.find((p) => p.id === plantId);
        const patched = {
          ...dashboardMock,
          plant_id: plantId,
          plant_name: plant?.name ?? plantId,
          avc_mw: plant?.avc_mw ?? dashboardMock.avc_mw,
        } as DashboardResponse;
        setData(patched);
      } else {
        const response = await getDashboard(plantId, date, signal);
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
    fetchDashboard(controller.signal);
    return () => controller.abort();
  }, [fetchDashboard]);

  const refetch = () => fetchDashboard();

  return { data, loading, error, refetch };
};
