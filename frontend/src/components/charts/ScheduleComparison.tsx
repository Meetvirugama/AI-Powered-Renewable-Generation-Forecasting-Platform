import { useMemo } from "react";
import Chart from "react-apexcharts";
import type { ApexOptions } from "apexcharts";
import { baseOptions, TOKENS } from "../../lib/apexTheme";
import { inr, inrCompact } from "../../lib/format";

interface Props {
  naiveTotalInr: number;
  optimisedTotalInr: number;
  savingsInr: number;
  savingsPct: number;
}

/**
 * The product's whole argument in one panel. The delta gets its own figure — never make
 * a judge subtract two bars by eye.
 */
export default function ScheduleComparison({
  naiveTotalInr,
  optimisedTotalInr,
  savingsInr,
  savingsPct,
}: Props) {
  const { series, options } = useMemo(() => {
    const s = [
      {
        name: "Expected deviation charge",
        data: [
          { x: "Naive P50", y: Number(naiveTotalInr.toFixed(2)) },
          { x: "Optimised", y: Number(optimisedTotalInr.toFixed(2)) },
        ],
      },
    ];

    const o: ApexOptions = {
      ...baseOptions,
      chart: { ...baseOptions.chart, type: "bar", height: 220 },
      legend: { show: false },
      plotOptions: {
        bar: {
          horizontal: true,
          borderRadius: 6,
          barHeight: "52%",
          distributed: true,
        },
      },
      // Penalty stays rose; the optimised bar is the good outcome, so it takes lime.
      colors: [TOKENS.pen[4], TOKENS.accent],
      xaxis: {
        labels: {
          formatter: (v: string) => inrCompact(Number(v)),
          style: { colors: TOKENS.textMuted, fontSize: "11px" },
        },
        axisBorder: { color: TOKENS.border },
        axisTicks: { color: TOKENS.border },
      },
      yaxis: { labels: { style: { colors: TOKENS.text, fontSize: "12px" } } },
      tooltip: {
        ...baseOptions.tooltip,
        y: { formatter: (v: number) => inr(v) },
      },
    };

    return { series: s, options: o };
  }, [naiveTotalInr, optimisedTotalInr]);

  return (
    <div className="flex flex-col gap-3">
      <Chart options={options} series={series} type="bar" height={220} />
      <div className="rounded-control bg-surface-2 px-4 py-3">
        <div className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          Saved by optimising
        </div>
        <div
          className="mt-1 text-2xl font-semibold tracking-tight text-accent"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          −{inr(savingsInr)}
        </div>
        <div className="mt-0.5 text-xs text-text-muted">
          {savingsPct.toFixed(1)}% below naive P50 submission
        </div>
      </div>
    </div>
  );
}
