import { createContext, useContext, useState, ReactNode } from "react";

interface DashboardContextType {
  plantId: string;
  setPlantId: (id: string) => void;
  ruleYear: number;
  setRuleYear: (year: number) => void;
}

const DashboardContext = createContext<DashboardContextType | undefined>(undefined);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [plantId, setPlantId] = useState("GJ_SOLAR_A");
  const [ruleYear, setRuleYear] = useState(2026);

  return (
    <DashboardContext.Provider value={{ plantId, setPlantId, ruleYear, setRuleYear }}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboardContext() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboardContext must be used within DashboardProvider");
  return ctx;
}
