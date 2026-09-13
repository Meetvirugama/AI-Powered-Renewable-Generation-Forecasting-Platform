import React from "react";
import { useSidebar } from "../hooks/useSidebar";
import { Link, useLocation } from "react-router";

const AppSidebar: React.FC = () => {
  const { isExpanded, isMobileOpen, toggleMobileSidebar } = useSidebar();
  const location = useLocation();
  const pathname = location.pathname;

  return (
    <aside
      className={`absolute left-0 top-0 z-50 flex h-screen w-72 flex-col overflow-y-hidden bg-surface border-r border-border duration-300 ease-linear lg:static lg:translate-x-0 ${
        isMobileOpen ? "translate-x-0" : "-translate-x-full"
      } ${!isExpanded ? "lg:w-20 lg:shrink-0" : "lg:w-72"}`}
    >
      <div className="flex items-center justify-between gap-2 px-6 py-5 lg:py-6 border-b border-border h-16">
        <Link to="/home" className="flex items-center gap-2 overflow-hidden">
          {isExpanded || isMobileOpen ? (
            <h1 className="text-xl font-bold text-text truncate tracking-tight">Vidyut<span className="text-accent">Vaani</span></h1>
          ) : (
            <h1 className="text-xl font-bold text-accent">V</h1>
          )}
        </Link>
        <button
          onClick={toggleMobileSidebar}
          className="block lg:hidden text-text-muted hover:text-text font-bold"
        >
          ✕
        </button>
      </div>
      <div className="no-scrollbar flex flex-1 flex-col overflow-y-auto overflow-x-hidden duration-300 ease-linear">
        <nav className="mt-5 py-4 px-3 lg:mt-9 lg:px-4 flex flex-col h-full">
          <ul className="mb-6 flex flex-col gap-2">
            {[
              { path: "/", label: "Overview", icon: "M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z" },
              { path: "/forecast", label: "Forecast", icon: "M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z" },
              { path: "/risk", label: "Risk", icon: "M12 2L2 22h20L12 2zm0 3.8l7.2 14.2H4.8L12 5.8zm-1 6.2v4h2v-4h-2zm0 6v2h2v-2h-2z" },
              { path: "/actions", label: "Actions", icon: "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 9h-2V7h-2v5H6v2h2v5h2v-5h2v-2z" },
              { path: "/copilot", label: "DSM Copilot", icon: "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z" }
            ].map((link) => (
              <li key={link.path}>
                <Link
                  to={link.path}
                  className={`group relative flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 text-sm font-medium duration-300 ease-in-out hover:bg-surface-2 ${
                    pathname === link.path ? "bg-surface-2 text-accent" : "text-text"
                  } ${!isExpanded ? "justify-center" : ""}`}
                >
                  <svg className="w-5 h-5 shrink-0 fill-current" viewBox="0 0 24 24">
                    <path d={link.icon} />
                  </svg>
                  {/* isExpanded is forced false on mobile viewports regardless of drawer
                      state; when the drawer is fully open (isMobileOpen) it's rendered
                      at full width, so labels must show even though isExpanded is false. */}
                  <span className={`truncate transition-all duration-300 ${!isExpanded && !isMobileOpen ? "hidden" : "block"}`}>
                    {link.label}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          
          <div className="mt-auto mb-6">
            <Link
              to="/home"
              className={`group relative flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 text-sm font-medium duration-300 ease-in-out hover:bg-surface-2 ${
                pathname === "/home" ? "bg-surface-2 text-accent" : "text-text-muted hover:text-text"
              } ${!isExpanded ? "justify-center" : ""}`}
            >
              <svg className="w-5 h-5 shrink-0 fill-current" viewBox="0 0 24 24">
                <path d="M10.09 15.59L11.5 17l5-5-5-5-1.41 1.41L12.67 11H3v2h9.67l-2.58 2.59zM19 3H5c-1.11 0-2 .9-2 2v4h2V5h14v14H5v-4H3v4c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z" />
              </svg>
              <span className={`truncate transition-all duration-300 ${!isExpanded ? "hidden" : "block"}`}>
                Home
              </span>
            </Link>
          </div>
        </nav>
      </div>
    </aside>
  );
};

export default AppSidebar;
