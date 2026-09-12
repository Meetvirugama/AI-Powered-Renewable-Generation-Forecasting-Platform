import React from "react";
import Panel from "../common/Panel";

interface StatTileProps {
  label: string;
  /** Pre-formatted string — never compute rupee values in the component. */
  value: string;
  sub?: string;
  tone?: "default" | "good";
}

const StatTile: React.FC<StatTileProps> = ({ label, value, sub, tone = "default" }) => {
  return (
    <Panel className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.08em] leading-[1.3] text-text-muted">
        {label}
      </span>
      <span
        className={`font-mono text-[26px] font-semibold leading-[1.1] tracking-[-0.01em] ${
          tone === "good" ? "text-accent" : "text-text"
        }`}
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </span>
      {sub && <span className="text-[12px] leading-[1.4] text-text-muted">{sub}</span>}
    </Panel>
  );
};

export default StatTile;
