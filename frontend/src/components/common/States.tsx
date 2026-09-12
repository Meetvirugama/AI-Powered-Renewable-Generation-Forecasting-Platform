/**
 * Shared loading / error / empty states. Previously each page hand-rolled these, so the
 * message a user saw after an API failure depended on which page they happened to be on
 * — Overview explained the VITE_USE_MOCKS escape hatch, the other four did not.
 */

export function Skeleton({ h }: { h: number }) {
  return (
    <div
      className="animate-pulse rounded-[var(--radius-card)] bg-surface"
      style={{ height: h }}
      role="status"
      aria-label="Loading"
    />
  );
}

export function ErrorState({ onRetry }: { onRetry?: () => void }) {
  const base = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
  return (
    <div className="relative rounded-[var(--radius-card)] bg-surface p-6">
      <h2 className="text-[13px] font-medium uppercase tracking-[0.08em] text-dev-over">
        Link down
      </h2>
      <p className="mt-2 max-w-[60ch] text-sm leading-relaxed text-text-muted">
        No response from <span className="font-mono text-text">{base}</span>. Start the
        backend with <span className="font-mono text-text">uvicorn backend.main:app</span>,
        or set <span className="font-mono text-text">VITE_USE_MOCKS=true</span> to run
        offline against fixtures.
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-[var(--radius-control)] bg-accent px-4 py-2 text-[13px] font-medium text-on-accent transition-colors hover:bg-accent-dim focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-bg"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex min-h-[120px] items-center justify-center px-4 text-center text-sm text-text-muted">
      {message}
    </div>
  );
}
