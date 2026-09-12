import React from "react";
import { useSidebar } from "../hooks/useSidebar";
import { useHealth } from "../hooks/useHealth";

const AppHeader: React.FC = () => {
  const { toggleSidebar, toggleMobileSidebar } = useSidebar();
  const { data: health } = useHealth();

  const handleToggle = () => {
    if (window.innerWidth >= 1024) {
      toggleSidebar();
    } else {
      toggleMobileSidebar();
    }
  };

  return (
    <header className="sticky top-0 z-40 flex w-full bg-surface border-b border-border h-16">
      <div className="flex flex-grow items-center justify-between px-4 py-4 md:px-6 2xl:px-11">
        {/* Sidebar toggle */}
        <div className="flex items-center gap-2 sm:gap-4">
          <button
            aria-controls="sidebar"
            onClick={handleToggle}
            className="z-50 block rounded-[var(--radius-control)] border border-border bg-surface p-1.5 shadow-sm text-text-muted hover:text-text"
          >
            ☰
          </button>
        </div>

        {/* Engine status strip */}
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium">
          {/* API liveness */}
          <span
            className={`rounded-[var(--radius-chip)] px-2.5 py-1 border ${
              health.api
                ? "border-accent text-accent"
                : "border-border text-text-muted"
            }`}
          >
            {health.api ? "API Live" : "API offline"}
          </span>

          {/* RAG liveness */}
          <span
            className={`rounded-[var(--radius-chip)] px-2.5 py-1 border ${
              health.rag
                ? "border-wind text-wind"
                : "border-border text-text-muted"
            }`}
          >
            {health.rag ? "RAG Live" : "RAG offline"}
          </span>

          {/* Honesty badges — one per synthetic module */}
          {health.syntheticModules.map((mod) => (
            <span
              key={mod}
              title={`The ${mod} engine is serving synthetic data. See GET /health for details.`}
              className="rounded-[var(--radius-chip)] border border-dev-over px-2.5 py-1 text-dev-over"
            >
              Synthetic: {mod}
            </span>
          ))}
        </div>
      </div>
    </header>
  );
};

export default AppHeader;
