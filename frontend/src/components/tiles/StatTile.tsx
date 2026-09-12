import React from "react";

interface StatTileProps {
  label: string;
  /** Pre-formatted string — never compute rupee values in the component. */
  value: string;
  sub?: string;
  tone?: "default" | "good";
}

const StatTile: React.FC<StatTileProps> = ({
  label,
  value,
  sub,
  tone = "default",
}) => {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-[var(--pad-card)] flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] leading-[1.3] text-text-muted">
        {label}
      </span>
      <span
        className={`text-[28px] font-semibold leading-[1.1] tracking-[-0.02em] ${
          tone === "good" ? "text-accent" : "text-text"
        }`}
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </span>
      {sub && (
        <span className="text-[12px] leading-[1.4] text-text-muted">{sub}</span>
      )}
    </div>
  );
};

export default StatTile;
