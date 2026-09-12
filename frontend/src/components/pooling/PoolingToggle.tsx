import React from "react";
import type { PoolingResponse } from "../../types/api";
import { inr } from "../../lib/format";

interface PoolingToggleProps {
  pooling: PoolingResponse | null;
  isPooled: boolean;
  onToggle: (pooled: boolean) => void;
}

const PoolingToggle: React.FC<PoolingToggleProps> = ({
  pooling,
  isPooled,
  onToggle,
}) => {
  if (!pooling) {
    return (
      <div className="rounded-[var(--radius-card)] border border-border bg-surface p-[var(--pad-card)]">
        <p className="text-[14px] text-text-muted">
          Pooling is not available for this plant.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-[var(--pad-card)] flex flex-col gap-4">
      {/* Toggle */}
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-semibold leading-[1.35] tracking-[-0.01em] text-text">
          Pooling Benefit
        </span>
        <button
          onClick={() => onToggle(!isPooled)}
          className={`relative inline-flex h-7 w-[52px] items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg ${
            isPooled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full transition-transform ${
              isPooled ? "translate-x-[27px] bg-on-accent" : "translate-x-1 bg-text-muted"
            }`}
          />
          <span className="sr-only">
            {isPooled ? "Pooled" : "Individual"}
          </span>
        </button>
      </div>

      {/* Label for toggle state */}
      <span className="text-[12px] text-text-muted">
        Mode: <span className="text-text font-medium">{isPooled ? "Pooled" : "Individual"}</span>
      </span>

      {/* Savings headline */}
      <div className="flex items-baseline gap-2">
        <span
          className="text-[28px] font-semibold leading-[1.1] tracking-[-0.02em] text-accent"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {pooling.savings_pct.toFixed(1)}%
        </span>
        <span className="text-[14px] text-text-muted">
          savings · {inr(pooling.savings_inr)}
        </span>
      </div>

      {/* Totals */}
      <div className="grid grid-cols-2 gap-[var(--gap-grid)]">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">
            Individual
          </span>
          <span className="text-[14px] text-text" style={{ fontVariantNumeric: "tabular-nums" }}>
            {inr(pooling.individual_total_inr)}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">
            Pooled
          </span>
          <span className="text-[14px] text-text" style={{ fontVariantNumeric: "tabular-nums" }}>
            {inr(pooling.pooled_total_inr)}
          </span>
        </div>
      </div>

      {/* Allocations */}
      {pooling.allocations.length > 0 && (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">
            Allocations
          </span>
          {pooling.allocations.map((alloc) => (
            <div
              key={alloc.plant_id}
              className="flex items-center justify-between h-10 text-[14px]"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              <span className="text-text">{alloc.plant_id}</span>
              <div className="flex items-center gap-3">
                <span className="text-text-muted">{inr(alloc.allocated_penalty_inr)}</span>
                <span className="text-accent">↓{inr(alloc.savings_inr)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default PoolingToggle;
