import type { ReactNode } from "react";

/**
 * The HUD panel. One shared surface for every page — previously each page hand-rolled
 * a near-identical card, which is both why they drifted and why the app read as a
 * generic admin template.
 *
 * Visual language: no full border. Four L-shaped corner brackets on a bare dark
 * surface, like a viewfinder reticle. Sharp corners (2px) — a bracket motif fights
 * heavy rounding.
 */

interface PanelProps {
  title?: string;
  sub?: string;
  /** Small monospace string pinned to the panel's top-right — a reading, an ID, a count. */
  readout?: string;
  children: ReactNode;
  className?: string;
  /** Faint oscilloscope grid behind the content. For chart panels only. */
  grid?: boolean;
}

function Brackets() {
  // Pure CSS corner marks. Two borders per corner, no SVG, no layout cost.
  const base = "pointer-events-none absolute h-3 w-3 border-border";
  return (
    <>
      <span className={`${base} left-0 top-0 border-l border-t`} aria-hidden="true" />
      <span className={`${base} right-0 top-0 border-r border-t`} aria-hidden="true" />
      <span className={`${base} bottom-0 left-0 border-b border-l`} aria-hidden="true" />
      <span className={`${base} bottom-0 right-0 border-b border-r`} aria-hidden="true" />
    </>
  );
}

export default function Panel({
  title,
  sub,
  readout,
  children,
  className = "",
  grid = false,
}: PanelProps) {
  return (
    <section
      className={`relative min-w-0 rounded-[var(--radius-card)] bg-surface p-5 ${
        grid ? "hud-grid" : ""
      } ${className}`}
    >
      <Brackets />
      {(title || readout) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            {title && (
              <h2 className="text-[13px] font-medium uppercase tracking-[0.08em] text-text">
                {title}
              </h2>
            )}
            {sub && <p className="mt-1 text-xs leading-relaxed text-text-muted">{sub}</p>}
          </div>
          {readout && (
            <span className="shrink-0 font-mono text-[11px] tabular-nums text-text-muted">
              {readout}
            </span>
          )}
        </header>
      )}
      {children}
    </section>
  );
}
