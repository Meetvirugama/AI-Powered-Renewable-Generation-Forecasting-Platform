import { useState } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { usePooling } from "../hooks/usePooling";
import { useSelectedPlant } from "../hooks/useSelectedPlant";
import ActionCards from "../components/actions/ActionCards";
import PoolingToggle from "../components/pooling/PoolingToggle";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST, inr, inrCompact } from "../lib/format";

// Battery capacity options exposed to the operator (0 = no battery, LP skipped).
const BATTERY_OPTIONS_MWH = [0, 12.5, 25, 37.5, 50];

// ─── stat tile ────────────────────────────────────────────────────────────────

function StatTile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
        {label}
      </span>
      <span
        className={`font-mono text-[22px] font-semibold leading-[1.1] tabular-nums ${
          accent ? "text-accent" : "text-text"
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

export default function Actions() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error, refetch } = useDashboard(plantId);
  const plant = useSelectedPlant(plantId);
  const date = data?.date ?? todayIST();
  const [isPooled, setIsPooled] = useState(true);
  const [batteryCap, setBatteryCap] = useState(0);

  // Both calls below are rule-year reactive — switching CERC rule year in the
  // shared header updates both. battery_capacity_mwh > 0 → LP solver couples
  // all 96 blocks via SOC continuity.
  const { data: opt, loading: optLoading } = useOptimize({
    plant_id: plantId,
    date,
    rule_year: ruleYear,
    battery_capacity_mwh: batteryCap > 0 ? batteryCap : null,
  });
  const { data: pooling } = usePooling(
    { pool_id: plant?.pool_id ?? "", date, rule_year: ruleYear },
    !!plant?.pool_id
  );

  if (loading && !data) {
    return (
      <div className="flex flex-col gap-[var(--gap-section)] h-full min-h-0">
        <Skeleton h={88} />
        <div className="grid grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[340px_1fr] flex-1 min-h-0">
          <div className="flex flex-col gap-[var(--gap-section)]">
            <Skeleton h={200} />
            <Skeleton h={200} />
          </div>
          <Skeleton h={440} />
        </div>
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  const batteryActive = batteryCap > 0;
  const hasBatteryDispatch =
    opt?.battery_dispatch?.some((b) => b.charge_mw > 0 || b.discharge_mw > 0) ?? false;

  // Key optimizer figures — always from DSM engine, never fabricated.
  const actionCount = (opt?.action_cards ?? data.actions).length;

  return (
    <div className="flex flex-col gap-[var(--gap-section)] h-full min-h-0">

      {/* ── stat strip header ───────────────────────────────────────────────── */}
      <Panel className="shrink-0">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {/* left: plant identity */}
          <div className="min-w-0">
            <h1 className="text-[20px] font-semibold leading-tight tracking-[-0.02em] text-text truncate">
              {data.plant_name}
            </h1>
            <p className="mt-0.5 font-mono text-[12px] text-text-muted tabular-nums">
              {data.date} · CERC DSM {ruleYear}
            </p>
          </div>

          {/* right: key optimizer metrics */}
          {optLoading ? (
            <div className="flex items-center gap-2 text-[12px] text-text-muted">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
              Computing optimiser…
            </div>
          ) : opt ? (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3 sm:divide-x sm:divide-border">
              <StatTile
                label="Naïve penalty"
                value={inrCompact(opt.naive_total_inr)}
                sub="un-optimised P50"
              />
              <div className="sm:pl-6">
                <StatTile
                  label="Optimised penalty"
                  value={inrCompact(opt.optimised_total_inr)}
                  sub={batteryActive ? `with ${batteryCap} MWh BESS` : "schedule only"}
                />
              </div>
              <div className="sm:pl-6">
                <StatTile
                  label="Savings"
                  value={`↓ ${opt.savings_pct.toFixed(1)}%`}
                  sub={inr(opt.savings_inr)}
                  accent
                />
              </div>
              <div className="sm:pl-6">
                <StatTile
                  label="Actions"
                  value={String(actionCount)}
                  sub={`grid action${actionCount !== 1 ? "s" : ""}`}
                />
              </div>
            </div>
          ) : null}
        </div>
      </Panel>

      {/* ── two-column body ──────────────────────────────────────────────────── */}
      <div className="grid flex-1 min-h-0 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[340px_1fr]">

        {/* ── left column: battery + pooling controls ── */}
        <div className="flex flex-col gap-[var(--gap-section)] min-h-0 overflow-y-auto">

          {/* battery storage control */}
          <Panel
            title="Battery storage (BESS)"
            sub="Set available capacity. > 0 enables LP solver with SOC continuity across all 96 blocks."
          >
            <div className="flex flex-col gap-4">
              {/* slider row */}
              <div className="flex items-center gap-3">
                <input
                  id="battery-slider"
                  type="range"
                  min={0}
                  max={BATTERY_OPTIONS_MWH.length - 1}
                  step={1}
                  value={BATTERY_OPTIONS_MWH.indexOf(batteryCap)}
                  onChange={(e) =>
                    setBatteryCap(BATTERY_OPTIONS_MWH[Number(e.target.value)])
                  }
                  className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-border accent-accent"
                  aria-label="Battery capacity in MWh"
                />
                <span
                  className="w-[72px] shrink-0 text-right font-mono text-[13px] text-text tabular-nums"
                >
                  {batteryCap === 0 ? "Off" : `${batteryCap} MWh`}
                </span>
              </div>

              {/* tick labels */}
              <div className="flex justify-between px-0.5">
                {BATTERY_OPTIONS_MWH.map((v) => (
                  <span
                    key={v}
                    className="text-[10px] text-text-muted tabular-nums"
                  >
                    {v === 0 ? "Off" : `${v}`}
                  </span>
                ))}
              </div>

              {/* status badges */}
              <div className="flex flex-wrap gap-2">
                {batteryActive && (
                  <span className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent">
                    ⚡ LP active
                  </span>
                )}
                {batteryActive && hasBatteryDispatch && (
                  <span className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] bg-dev-under/15 px-2.5 py-0.5 text-[11px] font-medium text-dev-under">
                    ✓ Dispatch computed
                  </span>
                )}
                {!batteryActive && (
                  <span className="text-[11px] text-text-muted">
                    No BESS — schedule optimiser only
                  </span>
                )}
              </div>

              {/* battery savings summary when active */}
              {batteryActive && opt && !optLoading && (
                <div className="grid grid-cols-2 gap-2 rounded-[var(--radius-control)] bg-surface-2 p-3 font-mono text-[12px] tabular-nums">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-text-muted">Naïve total</span>
                    <span className="text-text">{inr(opt.naive_total_inr)}</span>
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="text-text-muted">Optimised + BESS</span>
                    <span className="text-text">{inr(opt.optimised_total_inr)}</span>
                  </div>
                  <div className="col-span-2 border-t border-border pt-2">
                    <span className="font-semibold text-accent">
                      ↓ {opt.savings_pct.toFixed(1)}% saved · {inr(opt.savings_inr)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </Panel>

          {/* pooling benefit */}
          <PoolingToggle
            pooling={pooling ?? data.pooling_benefit}
            isPooled={isPooled}
            onToggle={setIsPooled}
          />
        </div>

        {/* ── right column: scrollable action cards ── */}
        <Panel
          title="Recommended grid actions"
          sub="Emitted by the optimiser · ₹ impact from the DSM engine"
          readout={
            optLoading ? "…" : `${actionCount} action${actionCount !== 1 ? "s" : ""}`
          }
          className="flex flex-col min-h-0"
        >
          {/* inner scroll container fills remaining panel height */}
          <div className="flex-1 min-h-0 overflow-y-auto pr-1 -mr-1"
               style={{ maxHeight: "calc(100vh - 280px)" }}>
            {optLoading ? (
              <div className="flex flex-col gap-3">
                <Skeleton h={80} />
                <Skeleton h={80} />
                <Skeleton h={80} />
              </div>
            ) : (
              <ActionCards actions={opt?.action_cards ?? data.actions} />
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
