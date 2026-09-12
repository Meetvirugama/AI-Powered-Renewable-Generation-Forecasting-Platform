import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import { useDsmForPlant } from "../hooks/useDsmForPlant";
import { useSelectedPlant } from "../hooks/useSelectedPlant";
import StatTile from "../components/tiles/StatTile";
import BriefingCard from "../components/tiles/BriefingCard";
import PlantMap from "../components/map/PlantMap";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";
import { inr, inrCompact, inrSaved, blockToIST, todayIST, getToleranceBand } from "../lib/format";

export default function Overview() {
  const { plantId, setPlantId, ruleYear } = useDashboardContext();

  const { data, loading, error, refetch } = useDashboard(plantId);
  const plant = useSelectedPlant(plantId);
  const date = data?.date ?? todayIST();

  const { data: opt } = useOptimize({ plant_id: plantId, date, rule_year: ruleYear });
  const { dsm } = useDsmForPlant(plantId, ruleYear, date, data, opt);

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={120} />
        <Skeleton h={360} />
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  const dsmBlocks = dsm?.blocks ?? [];
  const worst = dsmBlocks.length
    ? dsmBlocks.reduce((a, b) => (b.expected_penalty_inr > a.expected_penalty_inr ? b : a), dsmBlocks[0])
    : null;
  // Solar and wind carry different CERC tolerance bands (10% vs 15%) — never hardcode
  // one and label it generically.
  const band = getToleranceBand(plant?.type);
  const overBand = dsmBlocks.filter((b) => Math.abs(b.deviation_pct_at_p50) > band.fraction * 100).length;

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
            {data.plant_name}
          </h1>
          <p className="mt-1 font-mono text-[13px] text-text-muted">
            {data.date} · {data.avc_mw} MW AVC · CERC {dsm?.rule_version ?? "—"} · X={dsm?.x_value?.toFixed(2) ?? "—"}
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
          value={opt ? inrSaved(opt.savings_inr) : "—"}
          sub={opt ? `${opt.savings_pct.toFixed(1)}% below naive` : undefined}
          tone="good"
        />
        <StatTile
          label="Worst block"
          value={inr(worst?.expected_penalty_inr ?? 0)}
          sub={worst ? `Block ${worst.block_no} · ${blockToIST(worst.block_no)} IST` : undefined}
        />
        <StatTile label="Blocks over band" value={`${overBand} / 96`} sub={band.label} />
      </div>

      <BriefingCard briefing={data.briefing} />

      <Panel
        title="Plant locations"
        sub="Gujarat renewable portfolio. Click a pin to select."
      >
        <PlantMap selectedPlantId={plantId} onSelectPlant={setPlantId} />
      </Panel>
    </div>
  );
}
