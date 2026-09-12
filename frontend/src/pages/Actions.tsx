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

// Battery capacity options exposed to the operator (0 = no battery, LP skipped).
const BATTERY_OPTIONS_MWH = [0, 12.5, 25, 37.5, 50];

export default function Actions() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error, refetch } = useDashboard(plantId);
  const plant = useSelectedPlant(plantId);
  const date = data?.date ?? todayIST();
  const [isPooled, setIsPooled] = useState(true);
  const [batteryCap, setBatteryCap] = useState(0);

  // Previously this page rendered data.actions and data.pooling_benefit — the
  // one-shot GET /dashboard snapshot — so switching the CERC rule year in the
  // shared header updated every other page except this one. Both calls below
  // are rule-year reactive.
  //
  // battery_capacity_mwh: when > 0, the LP solver couples the 96-block schedule
  // via SOC continuity. Default 0 disables it (no physical battery at this plant).
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
        sub="Set available BESS capacity. When > 0, the LP solver couples all 96 blocks via SOC continuity to minimise total DSM penalty."
      >
        <div className="flex flex-col gap-4">
          {/* slider row */}
          <div className="flex items-center gap-4">
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
              className="h-2 w-full max-w-xs cursor-pointer appearance-none rounded-full bg-border accent-accent"
              aria-label="Battery capacity in MWh"
            />
            <span
              className="min-w-[72px] font-mono text-[13px] text-text"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {batteryCap === 0 ? "No battery" : `${batteryCap} MWh`}
            </span>

            {/* status badges */}
            {batteryActive && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-accent">
                ⚡ LP active
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
            {BATTERY_OPTIONS_MWH.map((v) => (
              <span
                key={v}
                className="text-[10px] text-text-muted"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {v === 0 ? "Off" : `${v}`}
              </span>
            ))}
          </div>

          {/* savings comparison when battery active */}
          {batteryActive && opt && !optLoading && (
            <div className="flex items-center gap-6 rounded-[var(--radius-control)] bg-surface-2 px-4 py-3 font-mono text-[13px]">
              <div>
                <span className="text-text-muted">Naïve total </span>
                <span className="text-text">{inr(opt.naive_total_inr)}</span>
              </div>
              <div>
                <span className="text-text-muted">Optimised + battery </span>
                <span className="text-text">{inr(opt.optimised_total_inr)}</span>
              </div>
              <div>
                <span className="text-accent font-semibold">
                  ↓ {opt.savings_pct.toFixed(1)}% saved
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
