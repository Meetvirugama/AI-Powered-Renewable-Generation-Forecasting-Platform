import React from "react";
import { Link, useLocation } from "react-router";
import StatusRail from "../components/common/StatusRail";

const NAV_LINKS = [
  {
    path: "/",
    label: "Overview",
    icon: (
      <svg className="w-4 h-4 shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z" />
      </svg>
    ),
  },
  {
    path: "/forecast",
    label: "Forecast",
    icon: (
      <svg className="w-4 h-4 shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z" />
      </svg>
    ),
  },
  {
    path: "/risk",
    label: "Risk",
    icon: (
      <svg className="w-4 h-4 shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M12 2L2 22h20L12 2zm0 3.8l7.2 14.2H4.8L12 5.8zm-1 6.2v4h2v-4h-2zm0 6v2h2v-2h-2z" />
      </svg>
    ),
  },
  {
    path: "/actions",
    label: "Actions",
    icon: (
      <svg className="w-4 h-4 shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 9h-2V7h-2v5H6v2h2v5h2v-5h2v-2z" />
      </svg>
    ),
  },
  {
    path: "/copilot",
    label: "DSM Copilot",
    icon: (
      <svg className="w-4 h-4 shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z" />
      </svg>
    ),
  },
] as const;

const AppHeader: React.FC = () => {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-40 flex w-full flex-col bg-surface border-b border-border">
      {/* ── top bar: logo + nav links ──────────────────────────────────── */}
      <div className="flex items-center gap-6 px-4 md:px-6 h-14">
        {/* Logo */}
        <Link
          to="/home"
          className="flex shrink-0 items-center gap-1.5 text-[18px] font-bold tracking-tight"
          aria-label="GridMind home"
        >
          Grid<span className="text-accent">Mind</span>
        </Link>

        {/* Divider */}
        <span className="h-5 w-px bg-border shrink-0" aria-hidden />

        {/* Nav items */}
        <nav aria-label="Main navigation">
          <ul className="flex items-center gap-1">
            {NAV_LINKS.map(({ path, label, icon }) => {
              const isActive = pathname === path;
              return (
                <li key={path}>
                  <Link
                    to={path}
                    aria-current={isActive ? "page" : undefined}
                    className={`
                      relative flex items-center gap-2 rounded-[var(--radius-control)]
                      px-3 py-1.5 text-[13px] font-medium transition-colors duration-150
                      focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg
                      ${
                        isActive
                          ? "bg-surface-2 text-accent"
                          : "text-text-muted hover:bg-surface-2 hover:text-text"
                      }
                    `}
                  >
                    {icon}
                    <span>{label}</span>
                    {/* Active underline */}
                    {isActive && (
                      <span
                        className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full bg-accent"
                        aria-hidden
                      />
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>

      {/* ── status rail ────────────────────────────────────────────────── */}
      <StatusRail />
    </header>
  );
};

export default AppHeader;
