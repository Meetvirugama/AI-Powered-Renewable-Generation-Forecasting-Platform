import { useMemo } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { useDSM } from "../hooks/useDSM";
import RiskHeatmap from "../components/charts/RiskHeatmap";
import ScheduleComparison from "../components/charts/ScheduleComparison";

function Panel({
  title,
  sub,
  children,
  className = "",
}: {
  title: string;
  sub?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`min-w-0 rounded-[var(--radius-card)] border border-border bg-surface p-5 ${className}`}
    >
      <header className="mb-4">
        <h2 className="text-[15px] font-semibold tracking-tight text-text">{title}</h2>
        {sub && <p className="mt-0.5 text-xs text-text-muted">{sub}</p>}
      </header>
      {children}
    </section>
  );
}

function Skeleton({ h }: { h: number }) {
  return (
    <div
      className="animate-pulse rounded-[var(--radius-card)] border border-border bg-surface"
      style={{ height: h }}
    />
  );
}

export default function Risk() {
  const { plantId, ruleYear } = useDashboardContext();

  const { data, loading, error } = useDashboard(plantId);

  const { data: opt } = useOptimize({
    plant_id: plantId,
    date: data?.date ?? new Date().toISOString().slice(0, 10),
    rule_year: ruleYear,
  });

  const dsmSchedule = useMemo(() => {
    if (opt?.optimised_schedule) return opt.optimised_schedule;
    if (data?.dsm_summary?.blocks) return data.dsm_summary.blocks.map((b) => b.schedule_mw);
    return [];
  }, [opt, data]);

  const { data: dsmOverride } = useDSM({
    plant_id: plantId,
    date: data?.date ?? new Date().toISOString().slice(0, 10),
    schedule_mw: dsmSchedule,
    rule_year: ruleYear,
  });

  const dsm = dsmOverride ?? data?.dsm_summary;

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={300} />
        <Skeleton h={300} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-surface p-6">
        <h2 className="text-[15px] font-semibold text-text">Cannot reach the API</h2>
      </div>
    );
  }

  if (!data) return null;

  const dsmBlocks = dsm?.blocks ?? [];

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header className="flex flex-wrap items-end justify-between gap-3 mb-2">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.03em] text-text">
            {data.plant_name}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {data.date} · CERC {dsm?.rule_version ?? "—"} · X = {dsm?.x_value?.toFixed(2) ?? "—"}
          </p>
        </div>
      </header>

      <Panel
        title="Risk heatmap"
        sub="Expected deviation charge per 15-minute block. Brighter is costlier."
      >
        <RiskHeatmap blocks={dsmBlocks} />
      </Panel>

      <Panel title="Naive P50 vs optimised" sub="Expected deviation charge for the day.">
        {opt ? (
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
