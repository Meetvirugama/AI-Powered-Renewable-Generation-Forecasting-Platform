import React from "react";
import { Link, useLocation } from "react-router";
import StatusRail from "../components/common/StatusRail";

const NAV_LINKS = [
  {
    path: "/",
    label: "Overview",
    icon: (
      <svg className="w-[15px] h-[15px] shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z" />
      </svg>
    ),
  },
  {
    path: "/forecast",
    label: "Forecast",
    icon: (
      <svg className="w-[15px] h-[15px] shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z" />
      </svg>
    ),
  },
  {
    path: "/risk",
    label: "Risk",
    icon: (
      <svg className="w-[15px] h-[15px] shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M12 2L2 22h20L12 2zm0 3.8l7.2 14.2H4.8L12 5.8zm-1 6.2v4h2v-4h-2zm0 6v2h2v-2h-2z" />
      </svg>
    ),
  },
  {
    path: "/actions",
    label: "Actions",
    icon: (
      <svg className="w-[15px] h-[15px] shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 9h-2V7h-2v5H6v2h2v5h2v-5h2v-2z" />
      </svg>
    ),
  },
  {
    path: "/copilot",
    label: "DSM Copilot",
    icon: (
      <svg className="w-[15px] h-[15px] shrink-0 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z" />
      </svg>
    ),
  },
] as const;

/** Arrow-right icon for the Home button */
function HomeArrowIcon() {
  return (
    <svg className="w-3.5 h-3.5 fill-current transition-transform duration-200 group-hover:translate-x-0.5" viewBox="0 0 24 24" aria-hidden>
      <path d="M10.09 15.59L11.5 17l5-5-5-5-1.41 1.41L12.67 11H3v2h9.67l-2.58 2.59zM19 3H5c-1.11 0-2 .9-2 2v4h2V5h14v14H5v-4H3v4c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z" />
    </svg>
  );
}

const AppHeader: React.FC = () => {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-40 flex w-full flex-col bg-surface border-b border-border">
      {/* ── main nav bar ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-0 px-4 md:px-6 h-14">

        {/* Logo */}
        <Link
          to="/"
          className="flex shrink-0 items-center gap-1 text-[17px] font-bold tracking-tight mr-5"
          aria-label="GridMind dashboard"
        >
          Grid<span className="text-accent">Mind</span>
        </Link>

        {/* Divider */}
        <span className="h-5 w-px bg-border shrink-0 mr-4" aria-hidden />

        {/* Nav tabs */}
        <nav aria-label="Main navigation" className="flex-1">
          <ul className="flex items-center gap-0.5">
            {NAV_LINKS.map(({ path, label, icon }) => {
              const isActive = pathname === path;
              return (
                <li key={path}>
                  <Link
                    to={path}
                    aria-current={isActive ? "page" : undefined}
                    className={`
                      relative flex items-center gap-1.5
                      rounded-[var(--radius-control)] px-3 py-1.5
                      text-[13px] font-medium
                      transition-colors duration-150
                      focus:outline-none focus-visible:ring-2 focus-visible:ring-accent
                      focus-visible:ring-offset-2 focus-visible:ring-offset-bg
                      ${
                        isActive
                          ? "bg-surface-2 text-accent"
                          : "text-text-muted hover:bg-surface-2 hover:text-text"
                      }
                    `}
                  >
                    {icon}
                    <span>{label}</span>
                    {/* 2-px accent underline on active */}
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

        {/* ── Home button — right-anchored, visually distinct ─────────── */}
        <div className="ml-4 shrink-0">
          <Link
            to="/home"
            aria-label="Go to home / landing page"
            className={`
              group flex items-center gap-2
              rounded-full border border-border
              bg-surface-2 px-3.5 py-1.5
              text-[12px] font-medium text-text-muted
              transition-all duration-200
              hover:border-accent/50 hover:bg-accent/10 hover:text-accent
              focus:outline-none focus-visible:ring-2 focus-visible:ring-accent
              focus-visible:ring-offset-2 focus-visible:ring-offset-bg
            `}
          >
            {/* Dot indicator */}
            <span
              className="h-1.5 w-1.5 rounded-full bg-border group-hover:bg-accent transition-colors duration-200"
              aria-hidden
            />
            <span>Home</span>
            <HomeArrowIcon />
          </Link>
        </div>
      </div>

      {/* ── status rail — second row ───────────────────────────────────── */}
      <StatusRail />
    </header>
  );
};

export default AppHeader;
