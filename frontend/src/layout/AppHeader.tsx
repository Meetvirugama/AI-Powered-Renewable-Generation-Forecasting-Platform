import React from "react";
import { useSidebar } from "../hooks/useSidebar";
import StatusRail from "../components/common/StatusRail";

const AppHeader: React.FC = () => {
  const { toggleSidebar, toggleMobileSidebar } = useSidebar();

  const handleToggle = () => {
    if (window.innerWidth >= 1024) {
      toggleSidebar();
    } else {
      toggleMobileSidebar();
    }
  };

  return (
    <header className="sticky top-0 z-40 flex w-full flex-col bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-3 md:px-6">
        <button
          aria-controls="sidebar"
          onClick={handleToggle}
          className="z-50 block rounded-[var(--radius-control)] border border-border bg-surface p-1.5 text-text-muted hover:text-text"
        >
          ☰
        </button>
      </div>
      {/* Real telemetry, not a hardcoded "Live" string — see StatusRail. */}
      <StatusRail />
    </header>
  );
};

export default AppHeader;
