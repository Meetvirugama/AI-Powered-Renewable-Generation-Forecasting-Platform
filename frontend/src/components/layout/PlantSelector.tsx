import { useEffect, useMemo, useRef, useState } from "react";
import type { Plant } from "../../types/api";
import { usePlants } from "../../hooks/usePlants";
import { plantTypeLabel } from "../../lib/format";

/**
 * Plant picker.
 *
 * This was a row of pill buttons, one per plant. That reads well for the four
 * seed plants and collapses completely once the real Gujarat inventory is
 * imported: 101 buttons wrap into a wall that pushes the charts off the page,
 * on every route, because the selector sits in the shared header.
 *
 * So: a combobox. Typing filters on name, type and capacity; the list is capped
 * and says how many it is hiding rather than rendering a hundred rows; and the
 * trigger keeps showing the selected plant so the header still answers "which
 * plant am I looking at?" at a glance.
 */

interface Props {
  value: string;
  onChange: (plantId: string) => void;
}

// Enough to scroll through, few enough to stay responsive. Anything beyond this
// is reached by typing, which is faster than scrolling a hundred rows anyway.
const MAX_VISIBLE = 40;

export default function PlantSelector({ value, onChange }: Props) {
  const { data, loading, error, refetch } = usePlants();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const plants = useMemo<Plant[]>(() => data?.plants ?? [], [data]);

  const selected = useMemo(
    () => plants.find((p) => p.id === value),
    [plants, value],
  );

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    // Largest first: a grid operator cares about the 1,000 MW park before the
    // 1 MW one, and it makes the unfiltered list immediately useful.
    const ordered = [...plants].sort((a, b) => b.avc_mw - a.avc_mw);
    if (!needle) return ordered;
    return ordered.filter((p) =>
      `${p.name} ${plantTypeLabel(p.type)} ${p.avc_mw}`
        .toLowerCase()
        .includes(needle),
    );
  }, [plants, query]);

  const visible = matches.slice(0, MAX_VISIBLE);
  const hidden = matches.length - visible.length;

  // Close on an outside click or Escape. Without this the panel stays open over
  // the charts, which is worse than the problem it replaced.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else setQuery("");
  }, [open]);

  // Adopt a real plant when the stored selection is not one.
  //
  // The default is the hardcoded seed id GJ_SOLAR_A. Once the real inventory is
  // imported that id is no longer in the list, and the trigger fell back to
  // "Select a plant" while the page below it happily rendered a dashboard --
  // because the backend still resolves seed ids through the YAML fallback. The
  // header and the page disagreeing about which plant you are looking at is
  // worse than either being wrong on its own.
  useEffect(() => {
    if (!plants.length) return;
    if (plants.some((p) => p.id === value)) return;
    const largest = plants.reduce((a, b) => (b.avc_mw > a.avc_mw ? b : a));
    onChange(largest.id);
  }, [plants, value, onChange]);

  if (loading && !data) {
    return (
      <div className="h-10 w-56 animate-pulse rounded-[var(--radius-control)] bg-surface-2" />
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

  if (!plants.length) {
    return (
      <div className="flex h-10 items-center text-[14px] text-text-muted">
        No plants available.
      </div>
    );
  }

  const choose = (plantId: string) => {
    onChange(plantId);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-10 min-w-[14rem] max-w-full items-center gap-2 rounded-[var(--radius-control)] border border-border bg-surface-2 px-3 text-[13px] font-medium text-text transition-colors hover:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg"
      >
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${
            selected?.type === "wind" ? "bg-wind" : "bg-solar"
          }`}
        />
        <span className="truncate">
          {selected ? selected.name : "Select a plant"}
          {selected && (
            <span className="ml-1 font-mono opacity-70">
              · {plantTypeLabel(selected.type)} · {selected.avc_mw}MW
            </span>
          )}
        </span>
        <span className="ml-auto shrink-0 text-text-muted" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div className="absolute left-0 z-[1000] mt-1 w-[22rem] max-w-[90vw] overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface shadow-xl">
          <div className="border-b border-border p-2">
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search ${plants.length} plants…`}
              className="h-9 w-full rounded-[var(--radius-chip)] border border-border bg-surface-2 px-3 text-[13px] text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </div>

          <ul role="listbox" className="max-h-72 overflow-y-auto py-1">
            {visible.length === 0 && (
              <li className="px-3 py-3 text-[13px] text-text-muted">
                Nothing matches “{query}”.
              </li>
            )}

            {visible.map((plant) => {
              const isActive = plant.id === value;
              return (
                <li key={plant.id} role="option" aria-selected={isActive}>
                  <button
                    type="button"
                    onClick={() => choose(plant.id)}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors focus:outline-none focus:bg-surface-2 ${
                      isActive
                        ? "bg-accent text-on-accent"
                        : "text-text hover:bg-surface-2"
                    }`}
                  >
                    {/* Colour dot — always paired with a text label */}
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${
                        isActive
                          ? "bg-on-accent/60"
                          : plant.type === "solar"
                            ? "bg-solar"
                            : "bg-wind"
                      }`}
                    />
                    <span className="truncate">{plant.name}</span>
                    <span
                      className={`ml-auto shrink-0 font-mono tabular-nums ${
                        isActive ? "text-on-accent/80" : "text-text-muted"
                      }`}
                    >
                      {plant.avc_mw}MW
                    </span>
                  </button>
                </li>
              );
            })}

            {hidden > 0 && (
              <li className="px-3 py-2 text-[12px] text-text-muted">
                {hidden} more — keep typing to narrow.
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
