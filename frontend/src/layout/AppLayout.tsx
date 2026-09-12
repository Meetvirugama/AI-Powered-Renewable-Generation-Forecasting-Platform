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
      <div className="relative flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
        <AppHeader />
        <main>
          <div className="p-4 mx-auto max-w-(--breakpoint-2xl) md:p-6">
            <Outlet />
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
