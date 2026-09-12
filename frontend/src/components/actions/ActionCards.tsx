import React from "react";
import type { ActionCard as ActionCardType } from "../../types/api";
import { blockToIST, inr } from "../../lib/format";
import { EmptyState } from "../common/States";

interface ActionCardsProps {
  actions: ActionCardType[];
}

const typeLabel = (type: ActionCardType["type"]): string =>
  type === "curtailment" ? "Curtailment" : "Reserve Flag";

const ActionCards: React.FC<ActionCardsProps> = ({ actions }) => {
  if (!actions || actions.length === 0) {
    return <EmptyState message="No action cards for this day." />;
  }

  return (
    <div className="grid grid-cols-1 gap-[var(--gap-grid)] md:grid-cols-2">
      {actions.map((card, idx) => {
        // curtailment -> amber (dev-over), reserve_flag -> blue (dev-under)
        const isCurtailment = card.type === "curtailment";
        const chipBg = isCurtailment ? "bg-dev-over/15" : "bg-dev-under/15";
        const chipText = isCurtailment ? "text-dev-over" : "text-dev-under";

        return (
          <div
            key={`${card.type}-${card.block_no}-${idx}`}
            className="relative flex flex-col gap-2 rounded-[var(--radius-control)] border-l-2 border-border bg-surface-2 p-4"
            style={{ borderLeftColor: isCurtailment ? "var(--color-dev-over)" : "var(--color-dev-under)" }}
          >
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-[var(--radius-chip)] px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-[0.06em] ${chipBg} ${chipText}`}
              >
                {typeLabel(card.type)}
              </span>
              <span className="font-mono text-[11px] text-text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
                Block {card.block_no} · {blockToIST(card.block_no)} IST
              </span>
            </div>

            <p className="text-[13px] leading-[1.5] text-text">{card.reason}</p>

            <div className="flex items-center gap-4 font-mono text-[12px] text-text-muted" style={{ fontVariantNumeric: "tabular-nums" }}>
              <span>
                <span className="text-text-muted">MW </span>
                <span className="text-text">{card.mw.toFixed(2)}</span>
              </span>
              <span>
                <span className="text-text-muted">Impact </span>
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
