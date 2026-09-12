import { useDSM } from "./useDSM";
import type { DashboardResponse, OptimizeResponse } from "../types/api";

/**
 * Resolves which DSM figures a page should trust: the dashboard's own summary, or a
 * fresher recomputation once the optimiser's schedule is known for the selected rule
 * year. Overview and Risk previously duplicated this composition by hand and had
 * already drifted from each other; Forecast and Actions skipped it entirely, so the
 * three pages sharing DashboardShell could show inconsistent penalty figures for the
 * same plant and date.
 *
 * The DSM re-fetch stays disabled until `opt` has a real schedule — firing it eagerly
 * with `schedule_mw: []` wastes a request and flashes an all-zero heatmap on load.
 */
export function useDsmForPlant(
  plantId: string,
  ruleYear: number,
  date: string,
  dashboard: DashboardResponse | null,
  opt: OptimizeResponse | null
) {
  const schedule = opt?.optimised_schedule ?? [];

  const { data: override, loading, error } = useDSM(
    {
      plant_id: plantId,
      date,
      schedule_mw: schedule,
      rule_year: ruleYear,
    },
    schedule.length > 0
  );

  return {
    dsm: override ?? dashboard?.dsm_summary ?? null,
    loading,
    error,
  };
}
