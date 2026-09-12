import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useOptimize } from "../hooks/useOptimize";
import ForecastFanChart from "../components/charts/ForecastFanChart";

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

export default function Forecast() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error } = useDashboard(plantId);
  const { data: opt } = useOptimize({
    plant_id: plantId,
    date: data?.date ?? new Date().toISOString().slice(0, 10),
    rule_year: ruleYear,
  });

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={400} />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-surface p-6">
        <h2 className="text-[15px] font-semibold text-text">Cannot reach the API</h2>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header className="flex flex-wrap items-end justify-between gap-3 mb-2">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.03em] text-text">
            {data.plant_name}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {data.date} · {data.avc_mw} MW available capacity
          </p>
        </div>
      </header>

      <Panel
        title="Forecast fan — P05 to P95"
        sub="Nested uncertainty bands with the P50 median and the optimised schedule as a dashed stepline."
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
