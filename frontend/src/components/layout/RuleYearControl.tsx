const YEARS = [2024, 2026, 2031] as const;

interface Props {
  value: number;
  onChange: (year: number) => void;
}

export default function RuleYearControl({ value, onChange }: Props) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] leading-[1.3] text-text-muted">
        CERC rule set
      </span>
      <div className="inline-flex rounded-[var(--radius-control)] border border-border bg-surface-2 p-0.5">
        {YEARS.map((year) => {
          const isActive = value === year;
          return (
            <button
              key={year}
              onClick={() => onChange(year)}
              className={`h-9 px-4 rounded-[var(--radius-chip)] text-[14px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg ${
                isActive
                  ? "bg-accent text-on-accent"
                  : "text-text-muted hover:text-text"
              }`}
            >
              {year}
            </button>
          );
        })}
      </div>
    </div>
  );
}
