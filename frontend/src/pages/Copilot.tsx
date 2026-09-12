import { useDashboardContext } from "../context/DashboardContext";
import { useDashboard } from "../hooks/useDashboard";
import RAGCopilot from "../components/copilot/RAGCopilot";
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
    <div className="flex h-full flex-col gap-4 min-h-0">
      {/* ── page header ──────────────────────────────────────────────────── */}
      <header className="shrink-0">
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-text">
          {data.plant_name}
        </h1>
        <p className="mt-1 font-mono text-[13px] text-text-muted">{data.date}</p>
      </header>

      {/* ── copilot panel — takes all remaining height ────────────────────── */}
      {/*
       * No <Panel> wrapper here: Panel adds p-5 padding + bracket decorations
       * but doesn't propagate height. Instead we replicate the surface directly
       * so flex-1 / min-h-0 actually works all the way to RAGCopilot.
       */}
      <section className="relative flex flex-1 flex-col min-h-0 rounded-[var(--radius-card)] bg-surface p-5">
        {/* corner brackets — Panel's visual identity */}
        <span className="pointer-events-none absolute left-0 top-0 h-3 w-3 border-l border-t border-border" aria-hidden />
        <span className="pointer-events-none absolute right-0 top-0 h-3 w-3 border-r border-t border-border" aria-hidden />
        <span className="pointer-events-none absolute bottom-0 left-0 h-3 w-3 border-b border-l border-border" aria-hidden />
        <span className="pointer-events-none absolute bottom-0 right-0 h-3 w-3 border-b border-r border-border" aria-hidden />

        {/* panel header */}
        <header className="shrink-0 mb-4">
          <h2 className="text-[13px] font-medium uppercase tracking-[0.08em] text-text">
            DSM Copilot
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-text-muted">
            Ask about regulations, penalties, or scheduling strategies. Citations link
            to CERC source documents.
          </p>
        </header>

        {/* chat — fills remaining space, scrolls internally */}
        <RAGCopilot plantId={plantId} ruleYear={ruleYear} />
      </section>
    </div>
  );
}
