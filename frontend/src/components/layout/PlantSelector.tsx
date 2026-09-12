import type { Plant } from "../../types/api";
import { usePlants } from "../../hooks/usePlants";
import { plantTypeLabel } from "../../lib/format";

interface Props {
  value: string;
  onChange: (plantId: string) => void;
}

export default function PlantSelector({ value, onChange }: Props) {
  const { data, loading, error, refetch } = usePlants();

  if (loading && !data) {
    return (
      <div className="flex h-10 w-52 items-center rounded-[var(--radius-control)] bg-surface-2 animate-pulse" />
    );
  }

  // Previously this case fell through the loading guard forever — usePlants sets
  // loading=false with data=null on failure, and nothing here checked `error`, so
  // the selector hung in its skeleton indefinitely while PlantMap on the same route
  // correctly showed a failure message.
  if (error && !data) {
    return (
      <button
        onClick={() => refetch()}
        className="flex h-10 items-center gap-2 rounded-[var(--radius-control)] border border-dev-over px-3 text-[13px] text-dev-over"
      >
        Plants unavailable — retry
      </button>
    );
  }

  if (!data || !data.plants.length) {
    return (
      <div className="flex h-10 items-center text-[14px] text-text-muted">
        No plants available.
      </div>
    );
  }

  return (
    <div className="inline-flex flex-wrap gap-1 rounded-[var(--radius-control)] border border-border bg-surface-2 p-0.5">
      {data.plants.map((plant: Plant) => {
        const isActive = plant.id === value;
        const dotColour = plant.type === "solar" ? "bg-solar" : "bg-wind";

        return (
          <button
            key={plant.id}
            onClick={() => onChange(plant.id)}
            className={`flex items-center gap-2 h-9 px-3 rounded-[var(--radius-chip)] text-[13px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg ${
              isActive
                ? "bg-accent text-on-accent"
                : "text-text-muted hover:text-text"
            }`}
          >
            {/* Colour dot — always paired with text label */}
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                isActive ? "bg-on-accent/60" : dotColour
              }`}
            />
            <span className="truncate">
              {plant.name}
              <span className="ml-1 font-mono opacity-70">
                · {plantTypeLabel(plant.type)} · {plant.avc_mw}MW
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
