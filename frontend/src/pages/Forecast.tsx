import { useMemo, useState } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useForecast, type Horizon } from "../hooks/useForecast";
import { useOptimize } from "../hooks/useOptimize";
import { useSelectedPlant } from "../hooks/useSelectedPlant";
import ForecastFanChart from "../components/charts/ForecastFanChart";
import ScheduleComparison from "../components/charts/ScheduleComparison";
import HorizonControl from "../components/layout/HorizonControl";
import Panel from "../components/common/Panel";
import StatReadout from "../components/tiles/StatReadout";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST, inrSaved, getToleranceBand, plantTypeLabel } from "../lib/format";

export default function Forecast() {
  const { plantId, ruleYear } = useDashboardContext();
  const [hours, setHours] = useState<Horizon>(24);

  const { data, loading, error, refetch } = useDashboard(plantId);
  const plant = useSelectedPlant(plantId);
  const date = data?.date ?? todayIST();
  const { data: opt, loading: optLoading } = useOptimize({
    plant_id: plantId,
    date,
    rule_year: ruleYear,
  });

  // 24h reads from the dashboard snapshot (already loaded). Longer horizons
  // fetch /forecast — the only route serving past one settlement day.
  const extended = hours > 24;
  const forecast = useForecast(extended ? plantId : "", date, hours);

  const blocks = useMemo(
    () => (extended ? forecast.data?.blocks ?? [] : data?.forecast.blocks ?? []),
    [extended, forecast.data, data]
  );
  const modelName = extended ? forecast.data?.model_name : data?.forecast.model_name;

  const stats = useMemo(() => {
    if (!blocks.length) return null;
    const p50s = blocks.map((b) => b.p50);
    const peakP50 = Math.max(...p50s);
    const peakBlock = blocks[p50s.indexOf(peakP50)];
    const peakTime = peakBlock?.ist_time?.slice(11, 16) ?? "—";
    const avgSpread = blocks.reduce((s, b) => s + (b.p95 - b.p05), 0) / blocks.length;
    const avcMw = data?.avc_mw || 1;
    const avgCF = (blocks.reduce((s, b) => s + b.p50, 0) / blocks.length / avcMw) * 100;
    return { peakP50, peakTime, avgSpread, avgCF };
  }, [blocks, data?.avc_mw]);

  const toleranceBand = getToleranceBand(plant?.type);

  if (loading && !data) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-[var(--gap-section)]">
        <Skeleton h={88} />
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[300px_1fr]">
          <div className="flex flex-col gap-[var(--gap-section)]">
            <Skeleton h={100} />
            <Skeleton h={260} />
          </div>
          <Skeleton h={440} />
        </div>
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-[var(--gap-section)]">
      {/* ── stat strip header ───────────────────────────────────────────────── */}
      <Panel className="shrink-0">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h1 className="truncate text-[20px] font-semibold leading-tight tracking-[-0.02em] text-text">
              {data.plant_name}
            </h1>
            <p className="mt-0.5 font-mono text-[12px] tabular-nums text-text-muted">
              {data.date} · {data.avc_mw} MW AVC ·{" "}
              <span
                className={`inline-flex items-center gap-1 rounded-[var(--radius-chip)] px-1.5 py-0 text-[11px] font-medium ${
                  plant?.type === "wind" ? "bg-wind/15 text-wind" : "bg-solar/15 text-solar"
                }`}
              >
                {plantTypeLabel(plant?.type)}
              </span>
            </p>
          </div>

          {stats ? (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3 sm:divide-x sm:divide-border">
              <StatReadout
                label="Peak P50"
                value={`${stats.peakP50.toFixed(1)} MW`}
                sub={`at ${stats.peakTime} IST`}
              />
              <div className="sm:pl-6">
                <StatReadout
                  label="Avg capacity factor"
                  value={`${stats.avgCF.toFixed(1)}%`}
                  sub={`of ${data.avc_mw} MW`}
                />
              </div>
              <div className="sm:pl-6">
                <StatReadout
                  label="Avg uncertainty"
                  value={`${stats.avgSpread.toFixed(1)} MW`}
                  sub="mean P95−P05 spread"
                  tone="muted"
                />
              </div>
              {opt && !optLoading && (
                <div className="sm:pl-6">
                  <StatReadout
                    label="Optimised saving"
                    value={inrSaved(opt.savings_inr)}
                    sub={`${opt.savings_pct.toFixed(1)}% vs naive P50`}
                    tone="good"
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-[12px] text-text-muted">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
              Loading forecast…
            </div>
          )}
        </div>
      </Panel>

      {/* ── two-column body ──────────────────────────────────────────────────── */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[300px_1fr]">
        {/* ── left column: view settings + schedule comparison ── */}
        <div className="flex min-h-0 flex-col gap-[var(--gap-section)] lg:overflow-y-auto">
          <Panel title="View settings">
            <div className="flex flex-col gap-5">
              <HorizonControl value={hours} onChange={setHours} />

              <div className="rounded-[var(--radius-control)] bg-surface-2 p-3 text-[12px]">
                <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                  CERC tolerance band
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[20px] font-semibold tabular-nums text-text">
                    ±{(toleranceBand.fraction * 100).toFixed(0)}%
                  </span>
                  <span className="text-text-muted">{toleranceBand.label}</span>
                </div>
                <p className="mt-1.5 leading-[1.4] text-text-muted">
                  Deviations within this band incur no DSM charge. Outside it, the CERC DSM{" "}
                  {ruleYear} tariff applies.
                </p>
              </div>

              {modelName && (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                    Model
                  </span>
                  <span className="rounded-[var(--radius-chip)] border border-border bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-text">
                    {modelName}
                  </span>
                </div>
              )}

              {extended && (
                <p className="text-[11px] leading-[1.4] text-text-muted">
                  The optimised schedule is a day-ahead submission for one settlement day, so it
                  is hidden on multi-day views.
                </p>
              )}
            </div>
          </Panel>

          {/* Schedule comparison is a one-day result, so 24h only. */}
          {!extended && (
            <Panel title="Schedule comparison" sub="Naive P50 vs optimised · ₹ from DSM engine">
              {optLoading ? (
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
                  Optimiser result unavailable.
                </div>
              )}
            </Panel>
          )}
        </div>

        {/* ── right column: fan chart ── */}
        <Panel
          title={`Forecast fan — next ${hours} hours`}
          sub={
            extended
              ? "P05–P95 uncertainty bands and P50 median. Optimised schedule shown on the 24h view only."
              : "P05–P95 nested bands with P50 median. Dashed stepline = optimised day-ahead schedule."
          }
          readout={modelName ?? undefined}
          grid
          className="flex min-h-0 flex-col"
        >
          <div className="min-h-[340px] flex-1">
            {extended && forecast.loading ? (
              <Skeleton h={360} />
            ) : extended && forecast.error ? (
              <ErrorState onRetry={forecast.refetch} />
            ) : !blocks.length ? (
              <div className="flex h-[340px] items-center justify-center text-sm text-text-muted">
                No forecast blocks available for this window.
              </div>
            ) : (
              <ForecastFanChart
                blocks={blocks}
                // Only on the 24h view. The schedule has 96 entries; handed to a
                // 192- or 288-block axis the rest draws as a committed zero schedule.
                optimisedSchedule={extended ? undefined : opt?.optimised_schedule}
                avcMw={data.avc_mw}
              />
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
