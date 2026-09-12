import { useRef, useEffect } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { useDsmForPlant } from "../hooks/useDsmForPlant";
import RiskHeatmap from "../components/charts/RiskHeatmap";
import ScheduleComparison from "../components/charts/ScheduleComparison";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST } from "../lib/format";
import type { DSMResponse } from "../types/api";

export default function Risk() {
  const { plantId, ruleYear } = useDashboardContext();

  const { data, loading, error, refetch } = useDashboard(plantId);
  const date = data?.date ?? todayIST();

  // rule_year is forwarded to both the optimiser and the DSM re-fetch so that
  // switching the CERC slider re-computes the heatmap under the new rule set.
  const { data: opt, loading: optLoading } = useOptimize({
    plant_id: plantId,
    date,
    rule_year: ruleYear,
  });

  const { dsm, loading: dsmLoading } = useDsmForPlant(
    plantId,
    ruleYear,
    date,
    data,
    opt
  );

  // Persist the last non-null DSM so the heatmap never flashes "No deviation
  // penalty" during the brief re-fetch triggered when the optimised schedule
  // arrives or when the rule year changes.
  const stableDsm = useRef<DSMResponse | null>(null);
  useEffect(() => {
    if (dsm) stableDsm.current = dsm;
  }, [dsm]);
  const displayDsm = dsm ?? stableDsm.current;

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={280} />
        <Skeleton h={280} />
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  const dsmBlocks = displayDsm?.blocks ?? [];
  const refetching = dsmLoading || optLoading;

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header>
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
          {data.plant_name}
        </h1>
        <p className="mt-1 font-mono text-[13px] text-text-muted">
          {data.date} · CERC {displayDsm?.rule_version ?? "—"} · X=
          {displayDsm?.x_value?.toFixed(2) ?? "—"}
        </p>
      </header>

      {/* ── risk heatmap ──────────────────────────────────────────────────── */}
      <Panel
        title="Risk heatmap"
        sub="Expected deviation charge per 15-minute block. Brighter is costlier."
        grid
      >
        {refetching && dsmBlocks.length === 0 ? (
          <Skeleton h={200} />
        ) : (
          <RiskHeatmap blocks={dsmBlocks} />
        )}
      </Panel>

      {/* ── naive vs optimised ────────────────────────────────────────────── */}
      <Panel
        title="Naive P50 vs optimised"
        sub={`Expected deviation charge for the day · rule set ${ruleYear}`}
        grid
      >
        {optLoading && !opt ? (
          <Skeleton h={220} />
        ) : opt ? (
          <ScheduleComparison
            naiveTotalInr={opt.naive_total_inr}
            optimisedTotalInr={opt.optimised_total_inr}
            savingsInr={opt.savings_inr}
            savingsPct={opt.savings_pct}
          />
        ) : (
          <div className="flex h-[220px] items-center justify-center text-sm text-text-muted">
            Loading optimiser result…
          </div>
        )}
      </Panel>
    </div>
  );
}
