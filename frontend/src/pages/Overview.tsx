import { useMemo } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { useDSM } from "../hooks/useDSM";
import StatTile from "../components/tiles/StatTile";
import BriefingCard from "../components/tiles/BriefingCard";
import PlantMap from "../components/map/PlantMap";
import { inr, inrCompact, blockToIST } from "../lib/format";

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

export default function Overview() {
  const { plantId, setPlantId, ruleYear } = useDashboardContext();

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
        <Skeleton h={120} />
        <Skeleton h={400} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-surface p-6">
        <h2 className="text-[15px] font-semibold text-text">Cannot reach the API</h2>
        <p className="mt-1 text-sm text-text-muted">
          The backend at {import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"} did
          not respond. Set <code>VITE_USE_MOCKS=true</code> to work offline.
        </p>
      </div>
    );
  }

  if (!data) return null;

  const dsmBlocks = dsm?.blocks ?? [];
  const worst = dsmBlocks.length
    ? dsmBlocks.reduce((a, b) =>
        b.expected_penalty_inr > a.expected_penalty_inr ? b : a,
      dsmBlocks[0])
    : null;
  const band = 0.1;
  const overBand = dsmBlocks.filter(
    (b) => Math.abs(b.deviation_pct_at_p50) > band * 100,
  ).length;

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header className="flex flex-wrap items-end justify-between gap-3 mb-2">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.03em] text-text">
            {data.plant_name}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {data.date} · {data.avc_mw} MW available capacity · CERC{" "}
            {dsm?.rule_version ?? "—"} · X = {dsm?.x_value?.toFixed(2) ?? "—"}
          </p>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-[var(--gap-grid)] lg:grid-cols-4">
        <StatTile
          label="Expected penalty"
          value={inr(dsm?.total_expected_penalty_inr ?? 0)}
          sub={opt ? `Naive submission: ${inrCompact(opt.naive_total_inr)}` : undefined}
        />
        <StatTile
          label="Saved by optimising"
          value={opt ? `−${inr(opt.savings_inr)}` : "—"}
          sub={opt ? `${opt.savings_pct.toFixed(1)}% below naive` : undefined}
          tone="good"
        />
        <StatTile
          label="Worst block"
          value={inr(worst?.expected_penalty_inr ?? 0)}
          sub={worst ? `Block ${worst.block_no} · ${blockToIST(worst.block_no)} IST` : undefined}
        />
        <StatTile
          label="Blocks over band"
          value={`${overBand} / 96`}
          sub="Solar band ±10%"
        />
      </div>

      <BriefingCard briefing={data.briefing} />

      <Panel title="Plant locations" sub="Gujarat renewable portfolio. Click a pin to select.">
        <PlantMap selectedPlantId={plantId} onSelectPlant={setPlantId} />
      </Panel>
    </div>
  );
}
