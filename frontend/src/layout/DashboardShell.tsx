import { Outlet } from "react-router";
import { DashboardProvider, useDashboardContext } from "../context/DashboardContext";
import PlantSelector from "../components/layout/PlantSelector";
import RuleYearControl from "../components/layout/RuleYearControl";

const USING_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

function ShellContent() {
  const { plantId, setPlantId, ruleYear, setRuleYear } = useDashboardContext();
  
  return (
    <div className="flex h-full flex-col gap-[var(--gap-section)]">
      <header className="shrink-0 flex flex-wrap items-center justify-between gap-3">
        <PlantSelector value={plantId} onChange={setPlantId} />
        <div className="flex flex-wrap items-center gap-3">
          <RuleYearControl value={ruleYear} onChange={setRuleYear} />
          {USING_MOCKS && (
            <span className="rounded-[var(--radius-chip)] border border-dev-over px-2.5 py-1 text-[11px] font-medium text-dev-over">
              Mock data — backend not connected
            </span>
          )}
        </div>
      </header>
      <main className="flex flex-1 flex-col min-h-0">
        <Outlet />
      </main>
    </div>
  );
}


export default function DashboardShell() {
  return (
    <DashboardProvider>
      <ShellContent />
    </DashboardProvider>
  );
}
