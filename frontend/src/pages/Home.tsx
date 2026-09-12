import { Link } from "react-router";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      {/* Hero Section */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
        <h1 className="text-5xl font-bold tracking-tight sm:text-7xl">
          Grid<span className="text-accent">Mind</span>
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-text-muted sm:text-xl">
          AI-Powered Renewable Generation Forecasting & Deviation Settlement Management. 
          Optimise your schedules against CERC regulations and minimise penalty risk.
        </p>
        <div className="mt-10 flex items-center justify-center gap-x-6">
          <Link
            to="/"
            className="rounded-[var(--radius-control)] bg-accent px-8 py-3.5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-dim shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Enter Dashboard
          </Link>
        </div>

        {/* Feature Grid */}
        <div className="mx-auto mt-24 max-w-7xl px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-[var(--radius-card)] border border-border bg-surface p-8 text-left">
              <h3 className="text-lg font-semibold text-text">P50 to P95 Forecast Fans</h3>
              <p className="mt-4 text-sm text-text-muted leading-relaxed">
                Visualize multi-quantile generation forecasts to understand uncertainty bands and risk spread across every 15-minute block.
              </p>
            </div>
            <div className="rounded-[var(--radius-card)] border border-border bg-surface p-8 text-left">
              <h3 className="text-lg font-semibold text-text">Regulatory Optimiser</h3>
              <p className="mt-4 text-sm text-text-muted leading-relaxed">
                Automatically generate schedules tuned to CERC 2024, 2026, or 2031 rules. Identify the most cost-effective submission strategy.
              </p>
            </div>
            <div className="rounded-[var(--radius-card)] border border-border bg-surface p-8 text-left">
              <h3 className="text-lg font-semibold text-text">RAG DSM Copilot</h3>
              <p className="mt-4 text-sm text-text-muted leading-relaxed">
                Query complex grid code regulations and penalty calculations instantly through our integrated RAG-powered chat assistant.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
