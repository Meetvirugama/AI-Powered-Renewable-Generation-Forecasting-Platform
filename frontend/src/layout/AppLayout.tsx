import { Outlet } from "react-router";
import AppHeader from "./AppHeader";

/**
 * Top-nav layout. AppHeader owns the logo, the navigation and the status rail;
 * there is no sidebar.
 */
const AppLayout: React.FC = () => {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      {/* Sticky top bar: logo + nav + StatusRail */}
      <AppHeader />

      {/* Page content — fills remaining height, own scroller */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden p-4 md:p-6">
          {/* Tailwind v4: a CSS variable needs max-w-(--x). max-w-[--x] is not wrapped in
              var(), emits no rule, and the page loses its 1536px cap on wide screens. */}
          <div className="mx-auto flex w-full max-w-(--breakpoint-2xl) flex-1 flex-col">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};

export default AppLayout;
