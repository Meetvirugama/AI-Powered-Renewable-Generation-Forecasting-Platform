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
import { todayIST } from "../lib/format";

export default function Actions() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error, refetch } = useDashboard(plantId);
  const plant = useSelectedPlant(plantId);
  const date = data?.date ?? todayIST();
  const [isPooled, setIsPooled] = useState(true);

  // Previously this page rendered data.actions and data.pooling_benefit — the
  // one-shot GET /dashboard snapshot — so switching the CERC rule year in the
  // shared header updated every other page except this one. Both calls below
  // are rule-year reactive.
  const { data: opt } = useOptimize({ plant_id: plantId, date, rule_year: ruleYear });
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

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header>
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
          {data.plant_name}
        </h1>
        <p className="mt-1 font-mono text-[13px] text-text-muted">{data.date}</p>
      </header>

      <Panel
        title="Recommended grid actions"
        sub="Emitted by the optimiser. Rupee impact comes from the DSM engine."
      >
        <ActionCards actions={opt?.action_cards ?? data.actions} />
      </Panel>

      <PoolingToggle
        pooling={pooling ?? data.pooling_benefit}
        isPooled={isPooled}
        onToggle={setIsPooled}
      />
    </div>
  );
}
