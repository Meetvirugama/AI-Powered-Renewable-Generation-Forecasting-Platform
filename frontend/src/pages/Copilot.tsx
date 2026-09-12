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
      <div className="flex h-full flex-col gap-3">
        <Skeleton h={60} />
        <Skeleton h={460} />
      </div>
    );
  }

  if (error && !data) return <ErrorState onRetry={refetch} />;
  if (!data) return null;

  return (
    // h-full + flex-col: fills the <main> inside DashboardShell exactly,
    // no page-level scrollbar. The chat message list scrolls internally.
    <div className="flex h-full min-h-0 flex-col gap-4">
      <header className="shrink-0">
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
          {data.plant_name}
        </h1>
        <p className="mt-1 font-mono text-[13px] text-text-muted">{data.date}</p>
      </header>

      {/* flex + min-h-0 on the Panel is what lets RAGCopilot's flex-1 claim the
          remaining height, so the input stays pinned to the bottom. */}
      <Panel
        title="DSM Copilot"
        sub="Ask about regulations, penalties, or scheduling strategies. Citations link to CERC source documents."
        className="flex min-h-0 flex-1 flex-col"
      >
        <RAGCopilot plantId={plantId} ruleYear={ruleYear} />
      </Panel>
    </div>
  );
}
