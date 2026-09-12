import type { Horizon } from "../../hooks/useForecast";

const HORIZONS: readonly Horizon[] = [24, 48, 72];

interface Props {
  value: Horizon;
  onChange: (hours: Horizon) => void;
}

/** 24 / 48 / 72-hour switch. Same segmented control as the CERC rule-set picker. */
export default function HorizonControl({ value, onChange }: Props) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] leading-[1.3] text-text-muted">
        Horizon
      </span>
      <div className="inline-flex rounded-[var(--radius-control)] border border-border bg-surface-2 p-0.5">
        {HORIZONS.map((hours) => {
          const isActive = value === hours;
          return (
            <button
              key={hours}
              type="button"
              aria-pressed={isActive}
              onClick={() => onChange(hours)}
              className={`h-9 px-4 rounded-[var(--radius-chip)] font-mono text-[14px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg ${
                isActive ? "bg-accent text-on-accent" : "text-text-muted hover:text-text"
              }`}
            >
              {hours}h
            </button>
          );
        })}
      </div>
    </div>
  );
}
