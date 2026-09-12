import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import ForecastFanChart from "../components/charts/ForecastFanChart";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST } from "../lib/format";

export default function Forecast() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error, refetch } = useDashboard(plantId);
  const date = data?.date ?? todayIST();
  const { data: opt } = useOptimize({ plant_id: plantId, date, rule_year: ruleYear });

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={380} />
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
        <p className="mt-1 font-mono text-[13px] text-text-muted">
          {data.date} · {data.avc_mw} MW available capacity
        </p>
      </header>

      <Panel
        title="Forecast fan — P05 to P95"
        sub="Nested uncertainty bands with the P50 median and the optimised schedule as a dashed stepline."
        grid
      >
        <ForecastFanChart
          blocks={data.forecast.blocks}
          optimisedSchedule={opt?.optimised_schedule}
          avcMw={data.avc_mw}
        />
      </Panel>
    </div>
  );
}
