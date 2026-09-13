import { useState } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { usePooling } from "../hooks/usePooling";
import { useSelectedPlant } from "../hooks/useSelectedPlant";
import ActionCards from "../components/actions/ActionCards";
import PoolingToggle from "../components/pooling/PoolingToggle";
import Panel from "../components/common/Panel";
import StatReadout from "../components/tiles/StatReadout";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST, inr, inrCompact } from "../lib/format";

// Battery sizes as hours of the plant's capacity, not fixed MWh. A fixed 50 MWh
// is a sizeable battery for a 50 MW plant and invisible on Khavda at 1,000 MW, so
// the slider would appear to do nothing on the largest plants.
const BATTERY_HOURS = [0, 0.25, 0.5, 1, 2];

export default function Actions() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error, refetch } = useDashboard(plantId);
  const plant = useSelectedPlant(plantId);
  const date = data?.date ?? todayIST();
  const [isPooled, setIsPooled] = useState(true);
  // The slider position, not a MWh value, so switching plant rescales the battery
  // to the new plant's capacity instead of carrying one plant's MWh to another.
  const [batteryStep, setBatteryStep] = useState(0);
  const avcMw = data?.avc_mw ?? plant?.avc_mw ?? 0;
  const batteryOptions = BATTERY_HOURS.map((h) => Math.round(h * avcMw * 10) / 10);
  const batteryCap = batteryOptions[batteryStep] ?? 0;

  // Both calls are rule-year reactive, so switching the CERC rule set in the
  // shared header updates this page like every other.
  //
  // battery_capacity_mwh: when > 0, the optimiser chooses each block's schedule
  // together with a battery that responds to each forecast outcome, carrying
  // state of charge from block to block. 0 means no battery is modelled.
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
      <div className="flex h-full min-h-0 flex-col gap-[var(--gap-section)]">
        <Skeleton h={88} />
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[340px_1fr]">
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
  const actionCount = (opt?.action_cards ?? data.actions).length;

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
              {data.date} · CERC DSM {ruleYear}
            </p>
          </div>

          {optLoading ? (
            <div className="flex items-center gap-2 text-[12px] text-text-muted">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
              Computing optimiser…
            </div>
          ) : opt ? (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3 sm:divide-x sm:divide-border">
              <StatReadout
                label="Naïve penalty"
                value={inrCompact(opt.naive_total_inr)}
                sub="declaring P50"
              />
              <div className="sm:pl-6">
                <StatReadout
                  label="Optimised penalty"
                  value={inrCompact(opt.optimised_total_inr)}
                  sub={batteryActive ? `with ${batteryCap} MWh battery` : "schedule only"}
                />
              </div>
              <div className="sm:pl-6">
                <StatReadout
                  label="Savings"
                  value={`↓ ${opt.savings_pct.toFixed(1)}%`}
                  sub={inr(opt.savings_inr)}
                  tone="good"
                />
              </div>
              <div className="sm:pl-6">
                <StatReadout
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
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-[var(--gap-section)] lg:grid-cols-[340px_1fr]">
        {/* ── left column: battery + pooling ── */}
        <div className="flex min-h-0 flex-col gap-[var(--gap-section)] lg:overflow-y-auto">
          <Panel
            title="Battery storage"
            sub="Sized in hours of plant capacity (2-hour battery). It absorbs over-injection and covers shortfall to keep deviation inside the CERC tolerance band; the schedule is re-optimised around it."
          >
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <input
                  id="battery-slider"
                  type="range"
                  min={0}
                  max={BATTERY_HOURS.length - 1}
                  step={1}
                  value={batteryStep}
                  onChange={(e) => setBatteryStep(Number(e.target.value))}
                  className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-border accent-accent"
                  aria-label="Battery capacity in hours of plant capacity"
                />
                <span className="shrink-0 text-right font-mono text-[12px] tabular-nums text-text">
                  {batteryCap === 0
                    ? "Off"
                    : `${batteryCap} MWh · ${Math.round((batteryCap / 2) * 10) / 10} MW`}
                </span>
              </div>

              <div className="flex justify-between px-0.5">
                {BATTERY_HOURS.map((h) => (
                  <span key={h} className="text-[10px] tabular-nums text-text-muted">
                    {h === 0 ? "Off" : `${h}h`}
                  </span>
                ))}
              </div>

              <div className="flex flex-wrap gap-2">
                {batteryActive && opt?.battery_modelled && (
                  <span className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent">
                    ⚡ Battery modelled
                  </span>
                )}
                {batteryActive && hasBatteryDispatch && (
                  <span className="inline-flex items-center gap-1 rounded-[var(--radius-chip)] bg-dev-under/15 px-2.5 py-0.5 text-[11px] font-medium text-dev-under">
                    ✓ Dispatch computed
                  </span>
                )}
                {!batteryActive && (
                  <span className="text-[11px] text-text-muted">No battery — schedule optimiser only</span>
                )}
              </div>

              {/* The battery's own contribution, shown separately rather than folded
                  into one total, so its effect is visible at every size. */}
              {batteryActive && opt && !optLoading && (
                <div className="grid grid-cols-2 gap-2 rounded-[var(--radius-control)] bg-surface-2 p-3 font-mono text-[12px] tabular-nums">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-text-muted">Naïve</span>
                    <span className="text-text">{inr(opt.naive_total_inr)}</span>
                  </div>
                  {opt.optimised_without_battery_inr != null && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-text-muted">Optimised, no battery</span>
                      <span className="text-text">{inr(opt.optimised_without_battery_inr)}</span>
                    </div>
                  )}
                  <div className="flex flex-col gap-0.5">
                    <span className="text-text-muted">With battery</span>
                    <span className="text-text">{inr(opt.optimised_total_inr)}</span>
                  </div>
                  {opt.battery_saving_inr != null && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-text-muted">Battery saves</span>
                      <span className="font-semibold text-accent">{inr(opt.battery_saving_inr)}</span>
                    </div>
                  )}
                  <div className="col-span-2 border-t border-border pt-2">
                    <span className="font-semibold text-accent">
                      ↓ {opt.savings_pct.toFixed(1)}% total · {inr(opt.savings_inr)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </Panel>

          <PoolingToggle
            pooling={pooling ?? data.pooling_benefit}
            isPooled={isPooled}
            onToggle={setIsPooled}
          />
        </div>

        {/* ── right column: action cards ── */}
        <Panel
          title="Recommended grid actions"
          sub="Emitted by the optimiser · ₹ impact from the DSM engine"
          readout={optLoading ? "…" : `${actionCount} action${actionCount !== 1 ? "s" : ""}`}
          className="flex min-h-0 flex-col"
        >
          {/* Scrolls inside the panel on large screens only; on a phone the page
              scrolls normally, so nothing is clipped. */}
          <div className="min-h-0 flex-1 lg:max-h-[calc(100vh-280px)] lg:overflow-y-auto lg:pr-1">
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
