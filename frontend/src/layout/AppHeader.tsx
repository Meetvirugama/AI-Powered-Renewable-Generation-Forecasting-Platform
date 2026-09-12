import React from "react";
import { useSidebar } from "../hooks/useSidebar";

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
    <header className="sticky top-0 z-40 flex w-full bg-surface border-b border-border h-16">
      <div className="flex flex-grow items-center justify-between px-4 py-4 md:px-6 2xl:px-11">
        <div className="flex items-center gap-2 sm:gap-4">
          <button
            aria-controls="sidebar"
            onClick={handleToggle}
            className="z-50 block rounded-[var(--radius-control)] border border-border bg-surface p-1.5 shadow-sm text-text-muted hover:text-text"
          >
            ☰
          </button>
        </div>

        <div className="hidden sm:block"></div>

        <div className="flex items-center gap-3 2xsm:gap-7">
          <div className="text-text-muted font-medium text-sm">
            Status: <span className="text-accent font-semibold">Live</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default AppHeader;
