import React from "react";
import type { ActionCard as ActionCardType } from "../../types/api";
import { blockToIST, inr } from "../../lib/format";
import { EmptyState } from "../common/States";

interface ActionCardsProps {
  actions: ActionCardType[];
}

// ─── type metadata ──────────────────────────────────────────────────────────

type CardMeta = {
  label: string;
  chipBg: string;
  chipText: string;
  borderColor: string;
  icon: string;
};

function cardMeta(type: ActionCardType["type"]): CardMeta {
  switch (type) {
    case "curtailment":
      return {
        label: "Curtailment",
        chipBg: "bg-dev-over/15",
        chipText: "text-dev-over",
        borderColor: "var(--color-dev-over)",
        icon: "↓",
      };
    case "reserve_flag":
      return {
        label: "Reserve Flag",
        chipBg: "bg-dev-under/15",
        chipText: "text-dev-under",
        borderColor: "var(--color-dev-under)",
        icon: "↑",
      };
    case "high_risk_block":
      return {
        label: "High Risk",
        chipBg: "bg-red-500/15",
        chipText: "text-red-400",
        borderColor: "#ef4444",
        icon: "⚠",
      };
    default:
      return {
        label: String(type),
        chipBg: "bg-surface-2",
        chipText: "text-text-muted",
        borderColor: "var(--color-border)",
        icon: "·",
      };
  }
}

// ─── single card ─────────────────────────────────────────────────────────────

const Card: React.FC<{ card: ActionCardType; idx: number }> = ({ card, idx }) => {
  const meta = cardMeta(card.type);

  return (
    <div
      key={`${card.type}-${card.block_no}-${idx}`}
      className="relative flex flex-col gap-2 rounded-[var(--radius-control)] border-l-2 border-border bg-surface-2 p-4"
      style={{ borderLeftColor: meta.borderColor }}
    >
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-[var(--radius-chip)] px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-[0.06em] ${meta.chipBg} ${meta.chipText}`}
        >
          <span aria-hidden>{meta.icon}</span>
          {meta.label}
        </span>
        <span
          className="font-mono text-[11px] text-text-muted"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          Block {card.block_no} · {blockToIST(card.block_no)} IST
        </span>
      </div>

      <p className="text-[13px] leading-[1.5] text-text">{card.reason}</p>

      <div
        className="flex items-center gap-4 font-mono text-[12px] text-text-muted"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
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
};

// ─── main component ───────────────────────────────────────────────────────────

/**
 * Renders action cards in two visual groups:
 *
 * 1. Scheduling actions (curtailment + reserve_flag) — what the optimiser did.
 * 2. Residual risk (high_risk_block) — blocks that remain expensive after
 *    scheduling; they need a physical remedy (battery or curtailment), not just
 *    a schedule change.
 *
 * The two groups have their own section labels so an operator reads them in
 * priority order rather than mixed by rupee impact.
 */
const ActionCards: React.FC<ActionCardsProps> = ({ actions }) => {
  if (!actions || actions.length === 0) {
    return <EmptyState message="No action cards for this day." />;
  }

  const scheduling = actions.filter(
    (c) => c.type === "curtailment" || c.type === "reserve_flag"
  );
  const residual = actions.filter((c) => c.type === "high_risk_block");
  const other = actions.filter(
    (c) => c.type !== "curtailment" && c.type !== "reserve_flag" && c.type !== "high_risk_block"
  );

  return (
    <div className="flex flex-col gap-5">
      {/* ── scheduling actions ── */}
      {scheduling.length > 0 && (
        <section>
          <div className="grid grid-cols-1 gap-[var(--gap-grid)] md:grid-cols-2">
            {scheduling.map((card, idx) => (
              <Card key={`sched-${idx}`} card={card} idx={idx} />
            ))}
          </div>
        </section>
      )}

      {/* ── residual risk (high_risk_block) ── */}
      {residual.length > 0 && (
        <section>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">
            Residual risk — physical intervention needed
          </p>
          <div className="grid grid-cols-1 gap-[var(--gap-grid)] md:grid-cols-2">
            {residual.map((card, idx) => (
              <Card key={`risk-${idx}`} card={card} idx={idx} />
            ))}
          </div>
        </section>
      )}

      {/* ── catch-all for any future types ── */}
      {other.length > 0 && (
        <section>
          <div className="grid grid-cols-1 gap-[var(--gap-grid)] md:grid-cols-2">
            {other.map((card, idx) => (
              <Card key={`other-${idx}`} card={card} idx={idx} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default ActionCards;
