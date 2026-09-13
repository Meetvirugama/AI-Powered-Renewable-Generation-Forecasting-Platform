/**
 * A flat label / value / caption readout for the stat strips at the top of the
 * Actions, Forecast and Risk pages.
 *
 * Deliberately not `StatTile`, which wraps itself in a Panel and is meant to stand
 * alone as a card; inside a strip that would nest a panel in a panel. This was
 * previously defined three times, once inside each page.
 */
export type StatTone = "default" | "good" | "danger" | "muted";

const TONE: Record<StatTone, string> = {
  default: "text-text",
  good: "text-accent",
  danger: "text-pen-5",
  muted: "text-text-muted",
};

interface StatReadoutProps {
  label: string;
  /** Pre-formatted string — never compute rupee values in the component. */
  value: string;
  sub?: string;
  tone?: StatTone;
}

export default function StatReadout({ label, value, sub, tone = "default" }: StatReadoutProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
        {label}
      </span>
      <span className={`font-mono text-[22px] font-semibold leading-[1.1] tabular-nums ${TONE[tone]}`}>
        {value}
      </span>
      {sub && <span className="text-[11px] tabular-nums text-text-muted">{sub}</span>}
    </div>
  );
}
