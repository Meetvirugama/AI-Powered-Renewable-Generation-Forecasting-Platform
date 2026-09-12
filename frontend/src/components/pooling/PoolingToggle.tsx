import React from "react";
import type { PoolingResponse } from "../../types/api";
import { inr } from "../../lib/format";
import Panel from "../common/Panel";
import { EmptyState } from "../common/States";

interface PoolingToggleProps {
  pooling: PoolingResponse | null;
  isPooled: boolean;
  onToggle: (pooled: boolean) => void;
}

/**
 * POST /pooling returns both individual_total_inr and pooled_total_inr in one
 * response — there is no separate "individual mode" request. The toggle's job is
 * therefore to switch which of those two figures is the headline, not to trigger a
 * refetch. Previously it did neither: every number here was read unconditionally
 * from `pooling` regardless of `isPooled`, so clicking the switch visibly did nothing.
 */
const PoolingToggle: React.FC<PoolingToggleProps> = ({ pooling, isPooled, onToggle }) => {
  if (!pooling) {
    return (
      <Panel title="Pooling benefit">
        <EmptyState message="Pooling is not available for this plant." />
      </Panel>
    );
  }

  const headlineTotal = isPooled ? pooling.pooled_total_inr : pooling.individual_total_inr;

  return (
    <Panel>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium uppercase tracking-[0.08em] text-text">
          Pooling Benefit
        </span>
        <button
          onClick={() => onToggle(!isPooled)}
          role="switch"
          aria-checked={isPooled}
          className={`relative inline-flex h-7 w-[52px] items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg ${
            isPooled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full transition-transform ${
              isPooled ? "translate-x-[27px] bg-on-accent" : "translate-x-1 bg-text-muted"
            }`}
          />
          <span className="sr-only">{isPooled ? "Pooled" : "Individual"}</span>
        </button>
      </div>

      <span className="mt-3 block text-[12px] text-text-muted">
        Mode: <span className="font-medium text-text">{isPooled ? "Pooled" : "Individual"}</span>
      </span>

      {/* Headline — the ONE figure the toggle actually changes. */}
      <div className="mt-4 flex items-baseline gap-2">
        <span
          className="font-mono text-[26px] font-semibold leading-[1.1] tracking-[-0.01em] text-text"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {inr(headlineTotal)}
        </span>
        <span className="text-[13px] text-text-muted">
          {isPooled ? "settled as one pool" : "settled individually"}
        </span>
      </div>

      {isPooled ? (
        <div className="mt-2 flex items-baseline gap-2 font-mono text-[13px]" style={{ fontVariantNumeric: "tabular-nums" }}>
          <span className="text-accent">{pooling.savings_pct.toFixed(1)}%</span>
          <span className="text-text-muted">saved vs individual · {inr(pooling.savings_inr)}</span>
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-text-muted">
          Switch to Pooled to see the saving from netting deviations across the pool.
        </p>
      )}

      {pooling.allocations.length > 0 && (
        <div className="mt-4 flex flex-col gap-2 border-t border-border pt-3">
          <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">
            Per-plant allocation
          </span>
          {pooling.allocations.map((alloc) => (
            <div
              key={alloc.plant_id}
              className="flex items-center justify-between font-mono text-[13px]"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              <span className="text-text">{alloc.plant_id}</span>
              <div className="flex items-center gap-3">
                <span className="text-text-muted">
                  {inr(isPooled ? alloc.allocated_penalty_inr : alloc.individual_penalty_inr)}
                </span>
                {isPooled && <span className="text-accent">↓{inr(alloc.savings_inr)}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
};

export default PoolingToggle;
