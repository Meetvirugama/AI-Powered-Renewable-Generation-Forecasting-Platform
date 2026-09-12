import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import RAGCopilot from "../components/copilot/RAGCopilot";
import Panel from "../components/common/Panel";
import { Skeleton, ErrorState } from "../components/common/States";

export default function Copilot() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error, refetch } = useDashboard(plantId);

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={460} />
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  return (
    <div className="flex h-full flex-col gap-[var(--gap-section)]">
      <header className="shrink-0">
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
          {data.plant_name}
        </h1>
        <p className="mt-1 font-mono text-[13px] text-text-muted">{data.date}</p>
      </header>

      <Panel
        title="DSM Copilot"
        sub="Ask about regulations, penalties, or scheduling strategies. Citations link to CERC source documents."
        className="min-h-[480px] flex-1"
      >
        <RAGCopilot plantId={plantId} ruleYear={ruleYear} />
      </Panel>
    </div>
  );
}
