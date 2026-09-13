import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

// ---------------------------------------------------------------------------
// Animated counter hook
// ---------------------------------------------------------------------------
function useCountUp(target: number, duration = 1800, start = false) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!start) return;
    let raf: number;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - t0) / duration, 1);
      // ease-out cubic
      const e = 1 - Math.pow(1 - p, 3);
      setVal(Math.round(e * target));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, start]);
  return val;
}

// ---------------------------------------------------------------------------
// Animated oscilloscope canvas background
// ---------------------------------------------------------------------------
function OscilloBackground() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf: number;
    let t = 0;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      const { width: W, height: H } = canvas;
      ctx.clearRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = "rgba(42,51,48,0.5)";
      ctx.lineWidth = 1;
      for (let x = 0; x < W; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      }
      for (let y = 0; y < H; y += 40) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      }

      // Animated sine lines (P05-P95 fan)
      const quantiles = [
        { q: 0.05, alpha: 0.12, w: 1 },
        { q: 0.25, alpha: 0.22, w: 1.5 },
        { q: 0.50, alpha: 0.55, w: 2.5 },
        { q: 0.75, alpha: 0.22, w: 1.5 },
        { q: 0.95, alpha: 0.12, w: 1 },
      ];
      quantiles.forEach(({ q, alpha, w }) => {
        ctx.beginPath();
        ctx.strokeStyle = `rgba(207,242,69,${alpha})`;
        ctx.lineWidth = w;
        for (let px = 0; px <= W; px += 2) {
          const phase = t * 0.0008 + q * Math.PI;
          const amp = H * 0.08 + q * H * 0.1;
          const freq = (2 * Math.PI) / (W * 0.45);
          const y = H * 0.5 + Math.sin(px * freq + phase) * amp
            + Math.sin(px * freq * 2.3 + phase * 1.4) * amp * 0.3;
          px === 0 ? ctx.moveTo(px, y) : ctx.lineTo(px, y);
        }
        ctx.stroke();
      });

      // Floating dots (DSM blocks)
      ctx.fillStyle = "rgba(207,242,69,0.18)";
      for (let i = 0; i < 14; i++) {
        const x = ((i * 137.508 + t * 0.012) % W);
        const y = ((i * 89.7 + Math.sin(t * 0.001 + i) * 40)) % H;
        const r = 1.5 + Math.sin(t * 0.002 + i * 0.8) * 1.2;
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      }

      t++;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);

  return (
    <canvas
      ref={ref}
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden
    />
  );
}

// ---------------------------------------------------------------------------
// Feature card
// ---------------------------------------------------------------------------
interface FeatureCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  tag: string;
  delay: number;
}

function FeatureCard({ icon, title, description, tag, delay }: FeatureCardProps) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  return (
    <div
      ref={ref}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(24px)",
        transition: "opacity 0.55s ease, transform 0.55s ease",
      }}
      className="group relative flex flex-col gap-4 rounded-[2px] border border-border bg-surface p-7 overflow-hidden
        hover:border-accent/30 transition-colors duration-300 cursor-default"
    >
      {/* Corner bracket decoration */}
      <span className="pointer-events-none absolute left-0 top-0 h-4 w-4 border-l-2 border-t-2 border-accent/20 group-hover:border-accent/60 transition-colors duration-300" aria-hidden />
      <span className="pointer-events-none absolute right-0 bottom-0 h-4 w-4 border-r-2 border-b-2 border-accent/20 group-hover:border-accent/60 transition-colors duration-300" aria-hidden />

      {/* Glow on hover */}
      <div className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{ background: "radial-gradient(ellipse at 50% 0%, rgba(207,242,69,0.06) 0%, transparent 70%)" }}
        aria-hidden />

      <div className="flex items-center justify-between">
        <span className="flex h-9 w-9 items-center justify-center rounded-[2px] bg-surface-2 text-accent">
          {icon}
        </span>
        <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-text-muted">
          {tag}
        </span>
      </div>
      <div>
        <h3 className="text-[15px] font-semibold text-text leading-snug">{title}</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-text-muted">{description}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat tile
// ---------------------------------------------------------------------------
function StatTile({ value, suffix, label, started }: { value: number; suffix: string; label: string; started: boolean }) {
  const n = useCountUp(value, 1600, started);
  return (
    <div className="flex flex-col items-center gap-1 px-8 py-4 border-r border-border last:border-r-0">
      <span className="font-mono text-[26px] font-bold tracking-tight text-accent" style={{ fontVariantNumeric: "tabular-nums" }}>
        {n.toLocaleString("en-IN")}{suffix}
      </span>
      <span className="text-[11px] uppercase tracking-wider text-text-muted">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Home page
// ---------------------------------------------------------------------------
const FEATURES = [
  {
    tag: "ML · Physics",
    title: "P05 → P95 Forecast Fans",
    description:
      "Multi-quantile probabilistic generation forecasts for every 15-minute block. IEC 61400-12 power curves for wind, LightGBM for solar. Understand uncertainty before committing a schedule.",
    icon: (
      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z" />
      </svg>
    ),
    delay: 600,
  },
  {
    tag: "CERC DSM",
    title: "Regulatory DSM Optimiser",
    description:
      "Scipy LP solver couples all 96 blocks via SOC continuity. Computes deviation charges under 2024, 2026, and 2031 CERC rules. Tells you the exact schedule to file to minimise penalty risk.",
    icon: (
      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 9h-2V7h-2v5H6v2h2v5h2v-5h2v-2z" />
      </svg>
    ),
    delay: 750,
  },
  {
    tag: "RAG · LLM",
    title: "DSM Copilot",
    description:
      "Ask any question about CERC regulations, deviation bands, or scheduling strategy. Citations link to the exact paragraph in the source document. ₹ figures come only from the DSM engine, never the LLM.",
    icon: (
      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z" />
      </svg>
    ),
    delay: 900,
  },
  {
    tag: "Grid · Portfolio",
    title: "Portfolio Pooling",
    description:
      "Aggregate multiple plants across a pool to offset individual deviations. See per-plant allocations and exactly how much pooling saves versus submitting separately.",
    icon: (
      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z" />
      </svg>
    ),
    delay: 1050,
  },
  {
    tag: "Battery LP",
    title: "Storage Dispatch",
    description:
      "Configure battery capacity and let the LP solver compute block-by-block charge/discharge across all 96 blocks. SOC continuity enforced — no fictitious energy created.",
    icon: (
      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4zm-1.67 8h-2v3h-2v-3H8l4-6 4 6z" />
      </svg>
    ),
    delay: 1200,
  },
  {
    tag: "Risk · Heatmap",
    title: "Block-Level Risk View",
    description:
      "96-block heatmap of expected deviation charges for the day. Instantly see the cloud events, ramp uncertainty, and overnight zeros — then act on them before gate closure.",
    icon: (
      <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24" aria-hidden>
        <path d="M12 2L2 22h20L12 2zm0 3.8l7.2 14.2H4.8L12 5.8zm-1 6.2v4h2v-4h-2zm0 6v2h2v-2h-2z" />
      </svg>
    ),
    delay: 1350,
  },
] as const;

const STATS = [
  { value: 96, suffix: "", label: "blocks / day" },
  { value: 7, suffix: " quantiles", label: "P05 → P95" },
  { value: 3, suffix: " rule sets", label: "CERC 2024–2031" },
  { value: 105, suffix: " plants", label: "Gujarat portfolio" },
];

export default function Home() {
  // Trigger hero text + stats animation after mount
  const [heroVisible, setHeroVisible] = useState(false);
  const [statsStarted, setStatsStarted] = useState(false);
  useEffect(() => {
    const t1 = setTimeout(() => setHeroVisible(true), 80);
    const t2 = setTimeout(() => setStatsStarted(true), 900);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-bg text-text">
      {/* ── mini top bar ───────────────────────────────────────────────── */}
      <header className="relative z-10 flex items-center justify-between px-6 py-4 border-b border-border/40">
        <span className="text-[17px] font-bold tracking-tight">
          Grid<span className="text-accent">Mind</span>
        </span>
        <Link
          to="/"
          className="flex items-center gap-2 rounded-full bg-accent px-4 py-1.5 text-[12px] font-semibold text-on-accent
            transition-all duration-200 hover:bg-accent-dim hover:scale-[1.03] active:scale-100
            focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
        >
          Enter Dashboard
          <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24" aria-hidden>
            <path d="M8 5v14l11-7z" />
          </svg>
        </Link>
      </header>

      {/* ── hero ───────────────────────────────────────────────────────── */}
      <section className="relative z-10 flex flex-col items-center justify-center px-6 py-20 text-center">
        {/* Animated oscilloscope background */}
        <div className="absolute inset-0 overflow-hidden" aria-hidden>
          <OscilloBackground />
          {/* Radial vignette so background fades at edges */}
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(ellipse 80% 60% at 50% 50%, transparent 30%, #0B0F0E 90%)",
            }}
          />
        </div>

        {/* Badge */}
        <div
          style={{
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "translateY(0)" : "translateY(-10px)",
            transition: "opacity 0.5s ease 0.05s, transform 0.5s ease 0.05s",
          }}
          className="mb-6 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-4 py-1.5"
        >
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
          <span className="font-mono text-[11px] font-medium tracking-wider text-accent uppercase">
            Hackout 2026 · AI Grid Operations
          </span>
        </div>

        {/* Title */}
        <h1
          style={{
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "translateY(0)" : "translateY(20px)",
            transition: "opacity 0.65s ease 0.15s, transform 0.65s ease 0.15s",
          }}
          className="text-[64px] font-bold leading-none tracking-[-0.04em] sm:text-[88px]"
        >
          Grid<span className="text-accent" style={{
            textShadow: "0 0 40px rgba(207,242,69,0.35), 0 0 80px rgba(207,242,69,0.15)",
          }}>Mind</span>
        </h1>

        {/* Tagline */}
        <p
          style={{
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "translateY(0)" : "translateY(20px)",
            transition: "opacity 0.65s ease 0.28s, transform 0.65s ease 0.28s",
          }}
          className="mt-5 max-w-xl text-[15px] leading-relaxed text-text-muted sm:text-[17px]"
        >
          AI-powered renewable generation forecasting & CERC deviation settlement
          management for Indian grid operators.
        </p>

        {/* CTA */}
        <div
          style={{
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "translateY(0)" : "translateY(20px)",
            transition: "opacity 0.65s ease 0.4s, transform 0.65s ease 0.4s",
          }}
          className="mt-10"
        >
          <Link
            to="/"
            className="group relative inline-flex items-center gap-2.5 overflow-hidden rounded-[4px]
              bg-accent px-8 py-3.5 text-[14px] font-semibold text-on-accent
              transition-all duration-200 hover:bg-accent-dim hover:scale-[1.04] active:scale-100
              focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
          >
            {/* Shimmer sweep */}
            <span
              className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent
                group-hover:translate-x-full transition-transform duration-700"
              aria-hidden
            />
            Enter Dashboard
            <svg className="w-4 h-4 fill-current transition-transform duration-200 group-hover:translate-x-1" viewBox="0 0 24 24" aria-hidden>
              <path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z" />
            </svg>
          </Link>
        </div>
      </section>

      {/* ── stats bar ──────────────────────────────────────────────────── */}
      <div
        style={{
          opacity: heroVisible ? 1 : 0,
          transition: "opacity 0.7s ease 0.55s",
        }}
        className="relative z-10 mx-6 mb-14 flex flex-wrap justify-center rounded-[2px] border border-border bg-surface divide-x divide-border overflow-hidden"
      >
        {STATS.map((s) => (
          <StatTile key={s.label} {...s} started={statsStarted} />
        ))}
      </div>

      {/* ── feature grid ───────────────────────────────────────────────── */}
      <section className="relative z-10 mx-auto w-full max-w-7xl px-6 pb-20 lg:px-8">
        <div
          style={{
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "translateY(0)" : "translateY(12px)",
            transition: "opacity 0.55s ease 0.45s, transform 0.55s ease 0.45s",
          }}
          className="mb-10 text-center"
        >
          <h2 className="text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
            Platform capabilities
          </h2>
          <p className="mt-2 text-[22px] font-semibold tracking-tight text-text">
            Everything a grid operator needs
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <FeatureCard key={f.title} {...f} />
          ))}
        </div>
      </section>

      {/* ── footer ─────────────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-border/40 px-6 py-5 text-center">
        <p className="font-mono text-[11px] text-text-muted">
          Grid<span className="text-accent">Mind</span> · Hackout 2026 ·{" "}
          <a
            href="https://github.com/Meetvirugama/AI-Powered-Renewable-Generation-Forecasting-Platform"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-accent transition-colors"
          >
            github.com/Meetvirugama
          </a>
        </p>
      </footer>
    </div>
  );
}
