import { useRef, useEffect } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { useDsmForPlant } from "../hooks/useDsmForPlant";
import RiskHeatmap from "../components/charts/RiskHeatmap";
import ScheduleComparison from "../components/charts/ScheduleComparison";
import Panel from "../components/common/Panel";
import StatReadout from "../components/tiles/StatReadout";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST, inrCompact, inr } from "../lib/format";
import type { DSMResponse } from "../types/api";

// The heatmap's rose ramp, as theme tokens rather than hex literals.
const PENALTY_RAMP = ["bg-pen-0", "bg-pen-1", "bg-pen-2", "bg-pen-3", "bg-pen-4", "bg-pen-5"];

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

  const { dsm, loading: dsmLoading } = useDsmForPlant(plantId, ruleYear, date, data, opt);

  // Persist the last non-null DSM so the heatmap never flashes empty during the
  // brief re-fetch triggered when the optimised schedule arrives or the rule year
  // changes -- but only for the same plant. The held value used to survive a
  // plant switch, so the previous plant's heatmap was shown under the new
  // plant's name until the new request finished.
  const stableDsm = useRef<DSMResponse | null>(null);
  useEffect(() => {
    if (dsm) stableDsm.current = dsm;
  }, [dsm]);
  const displayDsm =
    dsm ?? (stableDsm.current?.plant_id === plantId ? stableDsm.current : null);

  if (loading && !data) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-[var(--gap-section)]">
        <Skeleton h={88} />
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[300px_1fr]">
          <div className="flex flex-col gap-[var(--gap-section)]">
            <Skeleton h={140} />
            <Skeleton h={260} />
          </div>
          <Skeleton h={280} />
        </div>
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  const dsmBlocks = displayDsm?.blocks ?? [];
  const refetching = dsmLoading || optLoading;

  // Blocks that carry any expected DSM charge. An absolute count: the earlier
  // "above 60% of the day's worst block" was relative, so on a quiet day where
  // the worst block cost ₹10 most blocks would have been called high risk.
  const penalisedBlocks = dsmBlocks.filter((b) => b.expected_penalty_inr > 0).length;

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
              {data.date} · CERC {displayDsm?.rule_version ?? ruleYear} · X ={" "}
              <span className="text-text">{displayDsm?.x_value?.toFixed(2) ?? "—"}</span>
            </p>
          </div>

          {displayDsm ? (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3 sm:divide-x sm:divide-border">
              <StatReadout
                label="Expected penalty"
                value={inrCompact(displayDsm.total_expected_penalty_inr)}
                sub="all 96 blocks"
                tone="danger"
              />
              <div className="sm:pl-6">
                <StatReadout
                  label="P50 penalty"
                  value={inrCompact(displayDsm.total_p50_penalty_inr)}
                  sub="at median forecast"
                />
              </div>
              <div className="sm:pl-6">
                <StatReadout
                  label="Penalised blocks"
                  value={`${penalisedBlocks} / ${dsmBlocks.length}`}
                  sub="carry a DSM charge"
                  tone={penalisedBlocks > 0 ? "danger" : "default"}
                />
              </div>
              {opt && (
                <div className="sm:pl-6">
                  <StatReadout
                    label="Optimised saving"
                    value={`↓ ${opt.savings_pct.toFixed(1)}%`}
                    sub={inr(opt.savings_inr)}
                    tone="good"
                  />
                </div>
              )}
            </div>
          ) : refetching ? (
            <div className="flex items-center gap-2 text-[12px] text-text-muted">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-pen-5" />
              Computing DSM penalties…
            </div>
          ) : null}
        </div>
      </Panel>

      {/* ── two-column body ──────────────────────────────────────────────────── */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[300px_1fr]">
        {/* ── left column: rule context + schedule comparison ── */}
        <div className="flex min-h-0 flex-col gap-[var(--gap-section)] lg:overflow-y-auto">
          <Panel title="DSM rule context">
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-[var(--radius-control)] bg-surface-2 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                    Rule version
                  </div>
                  <div className="mt-1.5 font-mono text-[15px] font-semibold tabular-nums text-text">
                    {displayDsm?.rule_version ?? `DSM ${ruleYear}`}
                  </div>
                </div>
                <div className="rounded-[var(--radius-control)] bg-surface-2 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                    X-value
                  </div>
                  <div className="mt-1.5 font-mono text-[18px] font-semibold tabular-nums text-text">
                    {displayDsm?.x_value?.toFixed(2) ?? "—"}
                  </div>
                </div>
              </div>

              <div>
                <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                  Penalty ramp
                </div>
                <div className="flex gap-1">
                  {PENALTY_RAMP.map((cls, i) => (
                    <div
                      key={cls}
                      className={`h-3 flex-1 rounded-sm ${cls}`}
                      title={i === 0 ? "No charge" : `Tier ${i}`}
                    />
                  ))}
                </div>
                <div className="mt-1 flex justify-between text-[10px] tabular-nums text-text-muted">
                  <span>₹0</span>
                  <span>Max</span>
                </div>
                <p className="mt-2 text-[11px] leading-[1.4] text-text-muted">
                  Brighter = higher expected deviation charge. Dark cells are within the
                  CERC tolerance band or have no generation.
                </p>
              </div>

              {displayDsm && (
                <div className="rounded-[var(--radius-control)] bg-surface-2 p-3 font-mono text-[12px] tabular-nums">
                  <div className="flex justify-between border-b border-border pb-2">
                    <span className="text-text-muted">Expected total</span>
                    <span className="font-semibold text-pen-5">
                      {inr(displayDsm.total_expected_penalty_inr)}
                    </span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-text-muted">P50 total</span>
                    <span className="text-text">{inr(displayDsm.total_p50_penalty_inr)}</span>
                  </div>
                </div>
              )}
            </div>
          </Panel>

          <Panel
            title="Naive P50 vs optimised"
            sub={`Expected deviation charge for the day · rule set ${ruleYear}`}
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
                Optimiser result unavailable.
              </div>
            )}
          </Panel>
        </div>

        {/* ── right column: risk heatmap ── */}
        <Panel
          title="Risk heatmap"
          sub="Expected DSM charge per 15-minute block · brighter is costlier"
          readout={dsmBlocks.length ? `${dsmBlocks.length} blocks` : undefined}
          grid
          className="flex min-h-0 flex-col"
        >
          <div className="min-h-0 flex-1 lg:overflow-y-auto">
            {refetching && dsmBlocks.length === 0 ? (
              <Skeleton h={240} />
            ) : dsmBlocks.length === 0 ? (
              // No blocks means no DSM result, not a zero-charge day -- a day with
              // no charge still returns 96 blocks and renders as a dark heatmap.
              <div className="flex h-[200px] items-center justify-center text-sm text-text-muted">
                DSM result unavailable for this plant and date.
              </div>
            ) : (
              <RiskHeatmap blocks={dsmBlocks} />
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
