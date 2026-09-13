import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { useDsmForPlant } from "../hooks/useDsmForPlant";
import RiskHeatmap from "../components/charts/RiskHeatmap";
import ScheduleComparison from "../components/charts/ScheduleComparison";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST, inrCompact, inr } from "../lib/format";

// ─── stat tile ────────────────────────────────────────────────────────────────

function StatTile({
  label,
  value,
  sub,
  accent,
  danger,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
        {label}
      </span>
      <span
        className={`font-mono text-[22px] font-semibold leading-[1.1] tabular-nums ${
          accent ? "text-accent" : danger ? "text-[#FF5C7A]" : "text-text"
        }`}
      >
        {value}
      </span>
      {sub && (
        <span className="text-[11px] text-text-muted tabular-nums">{sub}</span>
      )}
    </div>
  );
}

// ─── page ─────────────────────────────────────────────────────────────────────

export default function Risk() {
  const { plantId, ruleYear } = useDashboardContext();

  const { data, loading, error, refetch } = useDashboard(plantId);
  const date = data?.date ?? todayIST();

  const { data: opt, loading: optLoading } = useOptimize({
    plant_id: plantId,
    date,
    rule_year: ruleYear,
  });
  const { dsm, loading: dsmLoading } = useDsmForPlant(plantId, ruleYear, date, data, opt);

  // ── loading ──────────────────────────────────────────────────────────────────
  if (loading && !data) {
    return (
      <div className="flex flex-col gap-[var(--gap-section)] h-full min-h-0">
        <Skeleton h={88} />
        <div className="grid grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[300px_1fr] flex-1 min-h-0">
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

  const dsmBlocks = dsm?.blocks ?? [];

  // High-risk block count: blocks where expected_penalty_inr is in the top two
  // rose tiers (pen-4 / pen-5) — i.e. above 60% of the max penalty.
  const maxPenalty = dsmBlocks.reduce((m, b) => Math.max(m, b.expected_penalty_inr), 0);
  const highRiskCount = dsmBlocks.filter(
    (b) => b.expected_penalty_inr > maxPenalty * 0.6
  ).length;

  return (
    <div className="flex flex-col gap-[var(--gap-section)] h-full min-h-0">

      {/* ── stat strip header ───────────────────────────────────────────────── */}
      <Panel className="shrink-0">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {/* left: plant + rule context */}
          <div className="min-w-0">
            <h1 className="text-[20px] font-semibold leading-tight tracking-[-0.02em] text-text truncate">
              {data.plant_name}
            </h1>
            <p className="mt-0.5 font-mono text-[12px] text-text-muted tabular-nums">
              {data.date} · CERC {dsm?.rule_version ?? ruleYear} · X ={" "}
              <span className="text-text">{dsm?.x_value?.toFixed(2) ?? "—"}</span>
            </p>
          </div>

          {/* right: key penalty metrics */}
          {dsmLoading || optLoading ? (
            <div className="flex items-center gap-2 text-[12px] text-text-muted">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-[#FF5C7A]" />
              Computing DSM penalties…
            </div>
          ) : dsm ? (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3 sm:divide-x sm:divide-border">
              <StatTile
                label="Expected penalty"
                value={inrCompact(dsm.total_expected_penalty_inr)}
                sub="all 96 blocks"
                danger
              />
              <div className="sm:pl-6">
                <StatTile
                  label="P50 penalty"
                  value={inrCompact(dsm.total_p50_penalty_inr)}
                  sub="at median forecast"
                />
              </div>
              <div className="sm:pl-6">
                <StatTile
                  label="High-risk blocks"
                  value={String(highRiskCount)}
                  sub="above 60% of peak"
                  danger={highRiskCount > 0}
                />
              </div>
              {opt && (
                <div className="sm:pl-6">
                  <StatTile
                    label="Optimised saving"
                    value={`↓ ${opt.savings_pct.toFixed(1)}%`}
                    sub={inr(opt.savings_inr)}
                    accent
                  />
                </div>
              )}
            </div>
          ) : null}
        </div>
      </Panel>

      {/* ── two-column body ──────────────────────────────────────────────────── */}
      <div className="grid flex-1 min-h-0 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[300px_1fr]">

        {/* ── left column: DSM rule context + schedule comparison ── */}
        <div className="flex flex-col gap-[var(--gap-section)] min-h-0 overflow-y-auto">

          {/* DSM rule metadata */}
          <Panel title="DSM rule context">
            <div className="flex flex-col gap-4">
              {/* rule version + x_value */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-[var(--radius-control)] bg-surface-2 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                    Rule version
                  </div>
                  <div className="mt-1.5 font-mono text-[18px] font-semibold text-text tabular-nums">
                    {dsm?.rule_version ?? `DSM ${ruleYear}`}
                  </div>
                </div>
                <div className="rounded-[var(--radius-control)] bg-surface-2 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                    X-value
                  </div>
                  <div className="mt-1.5 font-mono text-[18px] font-semibold text-text tabular-nums">
                    {dsm?.x_value?.toFixed(2) ?? "—"}
                  </div>
                </div>
              </div>

              {/* colour scale legend */}
              <div>
                <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                  Penalty ramp (rose scale)
                </div>
                <div className="flex gap-1">
                  {["#1B2321", "#402030", "#6B2A44", "#9C3355", "#CE3C63", "#FF5C7A"].map(
                    (c, i) => (
                      <div
                        key={i}
                        className="h-3 flex-1 rounded-sm"
                        style={{ background: c }}
                        title={i === 0 ? "None" : `Tier ${i}`}
                      />
                    )
                  )}
                </div>
                <div className="mt-1 flex justify-between text-[10px] text-text-muted tabular-nums">
                  <span>₹0</span>
                  <span>Max</span>
                </div>
                <p className="mt-2 text-[11px] leading-[1.4] text-text-muted">
                  Brighter = higher expected deviation charge. Dark cells are within
                  CERC tolerance or have zero generation.
                </p>
              </div>

              {/* penalty breakdown */}
              {dsm && (
                <div className="rounded-[var(--radius-control)] bg-surface-2 p-3 font-mono text-[12px] tabular-nums">
                  <div className="flex justify-between border-b border-border pb-2">
                    <span className="text-text-muted">Expected total</span>
                    <span className="text-[#FF5C7A] font-semibold">
                      {inr(dsm.total_expected_penalty_inr)}
                    </span>
                  </div>
                  <div className="flex justify-between pt-2">
                    <span className="text-text-muted">P50 total</span>
                    <span className="text-text">{inr(dsm.total_p50_penalty_inr)}</span>
                  </div>
                </div>
              )}
            </div>
          </Panel>

          {/* schedule comparison */}
          <Panel
            title="Schedule comparison"
            sub="Naive P50 vs optimised · ₹ from DSM engine"
          >
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
                Optimiser data unavailable.
              </div>
            )}
          </Panel>
        </div>

        {/* ── right column: risk heatmap ── */}
        <Panel
          title="Risk heatmap"
          sub="Expected DSM charge per 15-min block · Brighter = costlier · Hover for block details"
          readout={dsmBlocks.length ? `${dsmBlocks.length} blocks` : undefined}
          grid
          className="flex flex-col min-h-0"
        >
          <div className="flex-1 min-h-0 overflow-y-auto">
            {dsmLoading ? (
              <Skeleton h={240} />
            ) : !dsmBlocks.length ? (
              <div className="flex h-[200px] items-center justify-center text-sm text-text-muted">
                No deviation penalty in this window — zero DSM charge.
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


