import { useEffect, useState } from "react";
import { useHealth } from "../../hooks/useHealth";
import { usePlants } from "../../hooks/usePlants";
import { nowIST } from "../../lib/format";

/**
 * Persistent telemetry strip. Replaces the previously hardcoded "Status: Live" text,
 * which claimed the system was healthy even with the backend stopped.
 *
 * Grid frequency is deliberately NOT shown as a live reading — no endpoint supplies it.
 * Showing a plausible-looking 50.0x Hz would be inventing instrument data, which is the
 * same class of dishonesty as an LLM-authored rupee figure.
 */

function Segment({ label, value, tone = "default" }: {
  label: string;
  value: string;
  tone?: "default" | "good" | "bad";
}) {
  const toneClass =
    tone === "good" ? "text-accent" : tone === "bad" ? "text-dev-over" : "text-text";
  return (
    <span className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[10px] uppercase tracking-[0.1em] text-text-muted">{label}</span>
      <span className={`font-mono text-[11px] tabular-nums ${toneClass}`}>{value}</span>
    </span>
  );
}

export default function StatusRail() {
  const { data: health, loading: healthLoading } = useHealth();
  const { data: plants } = usePlants();
  const [clock, setClock] = useState(nowIST);
  const usingMocks = import.meta.env.VITE_USE_MOCKS === "true";

  useEffect(() => {
    const id = setInterval(() => setClock(nowIST()), 1000);
    return () => clearInterval(id);
  }, []);

  const apiUp = health.api;
  const linkLabel = healthLoading ? "CHECKING" : apiUp ? "CONNECTED" : "NO LINK";

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-border bg-bg px-4 py-2 lg:px-6">
      <span className="flex items-center gap-2 whitespace-nowrap">
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            apiUp ? "bg-accent motion-safe:animate-pulse" : "bg-dev-over"
          }`}
          aria-hidden="true"
        />
        <span
          className={`font-mono text-[11px] tracking-[0.08em] ${
            apiUp ? "text-accent" : "text-dev-over"
          }`}
        >
          {linkLabel}
        </span>
      </span>

      <Segment
        label="Copilot"
        value={health.rag ? "READY" : "OFFLINE"}
        tone={health.rag ? "good" : "bad"}
      />
      <Segment label="Plants" value={plants ? String(plants.total) : "—"} />
      <Segment label="IST" value={clock} />

      {usingMocks && (
        <span className="ml-auto whitespace-nowrap rounded-[var(--radius-chip)] border border-dev-over px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-dev-over">
          Fixture data
        </span>
      )}
    </div>
  );
}
