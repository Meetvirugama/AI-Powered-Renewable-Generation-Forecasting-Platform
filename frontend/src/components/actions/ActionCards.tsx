import React from "react";
import type { ActionCard as ActionCardType } from "../../types/api";
import { blockToIST, inr } from "../../lib/format";

interface ActionCardsProps {
  actions: ActionCardType[];
}

const typeLabel = (type: ActionCardType["type"]): string => {
  if (type === "curtailment") return "Curtailment";
  return "Reserve Flag";
};

const ActionCards: React.FC<ActionCardsProps> = ({ actions }) => {
  if (!actions || actions.length === 0) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-surface p-[var(--pad-card)]">
        <p className="text-[14px] text-text-muted">No action cards for this day.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-[var(--gap-grid)]">
      {actions.map((card, idx) => {
        // curtailment -> amber (dev-over), reserve_flag -> blue (dev-under)
        const isCurtailment = card.type === "curtailment";
        const chipBg = isCurtailment ? "bg-dev-over/20" : "bg-dev-under/20";
        const chipText = isCurtailment ? "text-dev-over" : "text-dev-under";

        return (
          <div
            key={`${card.type}-${card.block_no}-${idx}`}
            className="rounded-[var(--radius-card)] border border-border bg-surface p-[var(--pad-card)] flex flex-col gap-2"
          >
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-[var(--radius-chip)] px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-[0.06em] ${chipBg} ${chipText}`}
              >
                {typeLabel(card.type)}
              </span>
              <span className="text-[12px] text-text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
                Block {card.block_no} · {blockToIST(card.block_no)} IST
              </span>
            </div>

            <p className="text-[14px] leading-[1.5] text-text">
              {card.reason}
            </p>

            <div className="flex items-center gap-4 text-[12px] text-text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
              <span>
                <span className="text-text-muted">MW: </span>
                <span className="text-text">{card.mw.toFixed(2)}</span>
              </span>
              <span>
                <span className="text-text-muted">Impact: </span>
                <span className="text-text">{inr(card.inr_impact)}</span>
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default ActionCards;
