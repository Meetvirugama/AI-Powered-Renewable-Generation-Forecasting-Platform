import React from "react";
import type { DashboardBriefing } from "../../types/api";
import Panel from "../common/Panel";

interface BriefingCardProps {
  briefing: DashboardBriefing;
}

/**
 * Classifies a risk_level string into a chip tone. Previously did an exact match
 * against "LOW"/"HIGH"/"CRITICAL", so the backend's actual value
 * "HIGH_SAVINGS_OPPORTUNITY" fell through to the generic amber warning style —
 * a savings opportunity rendering as if it were a risk.
 */
const riskTone = (level: string): { classes: string; label: string } => {
  const l = level.toUpperCase();
  if (l.includes("SAVINGS") || l === "LOW") {
    return { classes: "bg-accent/15 text-accent", label: l.replace(/_/g, " ") };
  }
  if (l.includes("CRITICAL") || l.includes("HIGH")) {
    return { classes: "bg-pen-5/15 text-pen-5", label: l.replace(/_/g, " ") };
  }
  return { classes: "bg-dev-over/15 text-dev-over", label: l.replace(/_/g, " ") };
};

const BriefingCard: React.FC<BriefingCardProps> = ({ briefing }) => {
  const tone = riskTone(briefing.risk_level);
  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-semibold leading-[1.35] tracking-[-0.01em] text-text">
          {briefing.title}
        </h3>
        <span
          className={`inline-flex items-center rounded-[var(--radius-chip)] px-2.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-[0.06em] ${tone.classes}`}
        >
          {tone.label}
        </span>
      </div>
      <p className="mt-3 text-[14px] leading-[1.5] text-text-muted">{briefing.summary}</p>
    </Panel>
  );
};

export default BriefingCard;
