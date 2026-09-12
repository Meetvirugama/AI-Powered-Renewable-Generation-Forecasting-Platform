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
import { todayIST, inr } from "../lib/format";

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

  // Previously this page rendered data.actions and data.pooling_benefit — the
  // one-shot GET /dashboard snapshot — so switching the CERC rule year in the
  // shared header updated every other page except this one. Both calls below
  // are rule-year reactive.
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
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={260} />
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  const batteryActive = batteryCap > 0;
  const hasBatteryDispatch =
    opt?.battery_dispatch?.some((b) => b.charge_mw > 0 || b.discharge_mw > 0) ?? false;

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header>
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
          {data.plant_name}
        </h1>
        <p className="mt-1 font-mono text-[13px] text-text-muted">{data.date}</p>
      </header>

      {/* ── battery storage control ─────────────────────────────────────────── */}
      <Panel
        title="Battery storage"
        sub="Battery size in hours of plant capacity (2-hour battery). The battery absorbs over-injection and covers shortfall to keep deviation inside the CERC tolerance band; the schedule is re-optimised around it."
      >
        <div className="flex flex-col gap-4">
          {/* slider row */}
          <div className="flex flex-wrap items-center gap-4">
            <input
              id="battery-slider"
              type="range"
              min={0}
              max={BATTERY_HOURS.length - 1}
              step={1}
              value={batteryStep}
              onChange={(e) => setBatteryStep(Number(e.target.value))}
              className="h-2 w-full max-w-xs cursor-pointer appearance-none rounded-full bg-border accent-accent"
              aria-label="Battery capacity in hours of plant capacity"
            />
            <span
              className="min-w-[72px] font-mono text-[13px] text-text"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {batteryCap === 0
                ? "No battery"
                : `${batteryCap} MWh · ${Math.round((batteryCap / 2) * 10) / 10} MW`}
            </span>

            {/* status badges */}
            {batteryActive && opt?.battery_modelled && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent">
                ⚡ Battery modelled
              </span>
            )}
            {batteryActive && hasBatteryDispatch && (
              <span className="inline-flex items-center gap-1 rounded-full bg-dev-under/15 px-2.5 py-0.5 text-[11px] font-medium text-dev-under">
                ✓ Dispatch computed
              </span>
            )}
          </div>

          {/* tick labels */}
          <div className="flex w-full max-w-xs justify-between px-0.5">
            {BATTERY_HOURS.map((h) => (
              <span
                key={h}
                className="text-[10px] text-text-muted"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {h === 0 ? "Off" : `${h}h`}
              </span>
            ))}
          </div>

          {/* savings comparison when battery active */}
          {batteryActive && opt && !optLoading && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-[var(--radius-control)] bg-surface-2 px-4 py-3 font-mono text-[13px]">
              <div>
                <span className="text-text-muted">Naïve </span>
                <span className="text-text">{inr(opt.naive_total_inr)}</span>
              </div>
              {opt.optimised_without_battery_inr != null && (
                <div>
                  <span className="text-text-muted">Optimised, no battery </span>
                  <span className="text-text">{inr(opt.optimised_without_battery_inr)}</span>
                </div>
              )}
              <div>
                <span className="text-text-muted">With battery </span>
                <span className="text-text">{inr(opt.optimised_total_inr)}</span>
              </div>
              {opt.battery_saving_inr != null && (
                <div>
                  <span className="text-accent font-semibold">
                    battery saves {inr(opt.battery_saving_inr)}
                  </span>
                </div>
              )}
              <div>
                <span className="text-accent font-semibold">
                  ↓ {opt.savings_pct.toFixed(1)}% total
                </span>
              </div>
            </div>
          )}
        </div>
      </Panel>

      {/* ── action cards ────────────────────────────────────────────────────── */}
      <Panel
        title="Recommended grid actions"
        sub="Emitted by the optimiser. Rupee impact comes from the DSM engine."
      >
        {optLoading ? (
          <Skeleton h={160} />
        ) : (
          <ActionCards actions={opt?.action_cards ?? data.actions} />
        )}
      </Panel>

      {/* ── pooling benefit ─────────────────────────────────────────────────── */}
      <PoolingToggle
        pooling={pooling ?? data.pooling_benefit}
        isPooled={isPooled}
        onToggle={setIsPooled}
      />
    </div>
  );
}
