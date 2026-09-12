import { useState } from "react";
import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import { useForecast, type Horizon } from "../hooks/useForecast";
import { useOptimize } from "../hooks/useOptimize";
import ForecastFanChart from "../components/charts/ForecastFanChart";
import HorizonControl from "../components/layout/HorizonControl";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";
import { todayIST } from "../lib/format";

export default function Forecast() {
  const { plantId, ruleYear } = useDashboardContext();
  const [hours, setHours] = useState<Horizon>(24);

  const { data, loading, error, refetch } = useDashboard(plantId);
  const date = data?.date ?? todayIST();
  const { data: opt } = useOptimize({ plant_id: plantId, date, rule_year: ruleYear });

  // 24h keeps reading the dashboard response, which is already loaded. Longer
  // horizons go to /forecast, the only route that serves past one settlement day.
  const extended = hours > 24;
  const forecast = useForecast(extended ? plantId : "", date, hours);

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={380} />
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  const blocks = extended ? forecast.data?.blocks ?? [] : data.forecast.blocks;
  const modelName = extended ? forecast.data?.model_name : data.forecast.model_name;

  return (
    <div className="grid gap-[var(--gap-section)]">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
            {data.plant_name}
          </h1>
          <p className="mt-1 font-mono text-[13px] text-text-muted">
            {data.date} · {data.avc_mw} MW available capacity
          </p>
        </div>
        <HorizonControl value={hours} onChange={setHours} />
      </header>

      <Panel
        title={`Forecast fan — next ${hours} hours`}
        sub={
          extended
            ? "P05–P95 bands and P50 median. The optimised schedule is a day-ahead " +
              "submission for one settlement day, so it is shown on the 24h view only."
            : "Nested uncertainty bands with the P50 median and the optimised schedule as a dashed stepline."
        }
        readout={modelName}
        grid
      >
        {extended && forecast.loading ? (
          <Skeleton h={340} />
        ) : extended && forecast.error ? (
          <ErrorState onRetry={forecast.refetch} />
        ) : (
          <ForecastFanChart
            blocks={blocks}
            // The schedule has 96 entries. Passing it to a 192- or 288-block
            // chart would draw the rest of the line at zero, which reads as a
            // committed schedule of nothing for two days.
            optimisedSchedule={extended ? undefined : opt?.optimised_schedule}
            avcMw={data.avc_mw}
          />
        )}
      </Panel>
    </div>
  );
}
