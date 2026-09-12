import { SidebarProvider } from "../context/SidebarContext";
import { useSidebar } from "../hooks/useSidebar";
import { Outlet } from "react-router";
import AppHeader from "./AppHeader";
import Backdrop from "./Backdrop";
import AppSidebar from "./AppSidebar";

const LayoutContent: React.FC = () => {
  useSidebar();

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <AppSidebar />
      <Backdrop />
      <div className="relative flex flex-1 flex-col overflow-hidden">
        <AppHeader />
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
    </div>
  );
};

const AppLayout: React.FC = () => {
  return (
    <SidebarProvider>
      <LayoutContent />
    </SidebarProvider>
  );
};

export default AppLayout;
