import React from "react";
import type { DashboardBriefing } from "../../types/api";

interface BriefingCardProps {
  briefing: DashboardBriefing;
}

const riskChipClass = (level: string): string => {
  const l = level.toUpperCase();
  if (l === "LOW") return "bg-accent/20 text-accent";
  if (l === "HIGH" || l === "CRITICAL") return "bg-pen-5/20 text-pen-5";
  // MODERATE or anything else
  return "bg-dev-over/20 text-dev-over";
};

const BriefingCard: React.FC<BriefingCardProps> = ({ briefing }) => {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-[var(--pad-card)] flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-semibold leading-[1.35] tracking-[-0.01em] text-text">
          {briefing.title}
        </h3>
        <span
          className={`inline-flex items-center rounded-[var(--radius-chip)] px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-[0.06em] ${riskChipClass(briefing.risk_level)}`}
        >
          {briefing.risk_level}
        </span>
      </div>
      <p className="text-[14px] leading-[1.5] text-text-muted">
        {briefing.summary}
      </p>
    </div>
  );
};

export default BriefingCard;
