import { BrowserRouter as Router, Routes, Route } from "react-router";
import AppLayout from "./layout/AppLayout";
import { ScrollToTop } from "./components/common/ScrollToTop";
import DashboardShell from "./layout/DashboardShell";
import Home from "./pages/Home";
import Overview from "./pages/Overview";
import Forecast from "./pages/Forecast";
import Risk from "./pages/Risk";
import Actions from "./pages/Actions";
import Copilot from "./pages/Copilot";

export default function App() {
  return (
    <Router>
      <ScrollToTop />
      <Routes>
        <Route path="/home" element={<Home />} />
        <Route element={<AppLayout />}>
          <Route element={<DashboardShell />}>
            <Route index element={<Overview />} />
            <Route path="forecast" element={<Forecast />} />
            <Route path="risk" element={<Risk />} />
            <Route path="actions" element={<Actions />} />
            <Route path="copilot" element={<Copilot />} />
          </Route>
        </Route>
      </Routes>
    </Router>
  );
}
