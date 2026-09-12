import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import RAGCopilot from "../components/copilot/RAGCopilot";

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
      className={`min-w-0 flex flex-col rounded-[var(--radius-card)] border border-border bg-surface p-5 ${className}`}
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

export default function Copilot() {
  const { plantId, ruleYear } = useDashboardContext();
  const { data, loading, error } = useDashboard(plantId);

  if (loading && !data) {
    return (
      <div className="grid gap-[var(--gap-section)]">
        <Skeleton h={480} />
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
    <div className="flex flex-col h-full gap-[var(--gap-section)]">
      <header className="flex flex-wrap items-end justify-between gap-3 mb-2 shrink-0">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.03em] text-text">
            {data.plant_name}
          </h1>
          <p className="mt-1 text-sm text-text-muted">
            {data.date}
          </p>
        </div>
      </header>

      <Panel
        title="DSM Copilot"
        sub="Ask about regulations, penalties, or scheduling strategies. Citations link to CERC source documents."
        className="flex-1 min-h-[480px]"
      >
        <RAGCopilot plantId={plantId} ruleYear={ruleYear} />
      </Panel>
    </div>
  );
}
