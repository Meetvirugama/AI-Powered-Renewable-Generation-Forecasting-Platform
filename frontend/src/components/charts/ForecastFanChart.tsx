import { useMemo } from "react";
import Chart from "react-apexcharts";
import type { ApexOptions } from "apexcharts";
import { BlockForecast } from "../../types/api";
import { baseOptions, blockLabel, TOKENS } from "../../lib/apexTheme";

interface Props {
  blocks: BlockForecast[];
  /** Length 96, from POST /optimize. Rendered as a dashed stepline. */
  optimisedSchedule?: number[];
  avcMw: number;
}

/**
 * P05–P95 uncertainty bands with the P50 median and the optimised schedule on top.
 * rangeArea carries the bands; a mixed `line` series carries P50 and the schedule.
 * Night blocks stay on the axis — cropping them would imply solar runs 24 hours.
 */
export default function ForecastFanChart({ blocks, optimisedSchedule, avcMw }: Props) {
  const { series, options } = useMemo(() => {
    // ist_time is a full ISO timestamp ("2026-06-15T17:45:00+05:30"), not "HH:MM" —
    // the chart wants a short axis label. Slicing the fixed-width HH:MM substring
    // still honours the backend's own field (no independent block_no arithmetic)
    // without a Date-parsing/timezone round trip; block_no is only the fallback.
    const x = (b: BlockForecast) =>
      b.ist_time?.length >= 16 ? b.ist_time.slice(11, 16) : blockLabel(b.block_no);

    const band = (lo: keyof BlockForecast, hi: keyof BlockForecast) =>
      blocks.map((b) => ({ x: x(b), y: [b[lo] as number, b[hi] as number] }));

    const s: ApexOptions["series"] = [
      { name: "P05–P95", type: "rangeArea", data: band("p05", "p95") },
      { name: "P10–P90", type: "rangeArea", data: band("p10", "p90") },
      { name: "P25–P75", type: "rangeArea", data: band("p25", "p75") },
      {
        name: "P50 median",
        type: "line",
        data: blocks.map((b) => ({ x: x(b), y: Number(b.p50.toFixed(2)) })),
      },
    ];

    if (optimisedSchedule?.length) {
      s.push({
        name: "Optimised schedule",
        type: "line",
        data: blocks.map((b, i) => ({
          x: x(b),
          y: Number((optimisedSchedule[i] ?? 0).toFixed(2)),
        })),
      });
    }

    const o: ApexOptions = {
      ...baseOptions,
      chart: { ...baseOptions.chart, type: "rangeArea", height: 340, stacked: false },
      // Bands palest outward; the two line series sit above them.
      colors: [
        TOKENS.devUnder,
        TOKENS.devUnder,
        TOKENS.devUnder,
        TOKENS.text,
        TOKENS.accent,
      ],
      fill: { opacity: [0.13, 0.17, 0.22, 1, 1] },
      stroke: {
        // A schedule is piecewise constant per 15-min block, never a smooth curve.
        curve: ["smooth", "smooth", "smooth", "smooth", "stepline"],
        width: [0, 0, 0, 2, 2],
        dashArray: [0, 0, 0, 0, 5],
      },
      markers: { size: 0, hover: { size: 0 } },
      xaxis: {
        type: "category",
        tickAmount: 12,
        labels: {
          rotate: 0,
          hideOverlappingLabels: true,
          style: { colors: TOKENS.textMuted, fontSize: "11px" },
        },
        axisBorder: { color: TOKENS.border },
        axisTicks: { color: TOKENS.border },
        title: { text: "IST", style: { color: TOKENS.textMuted, fontSize: "11px" } },
      },
      yaxis: {
        min: 0,
        max: Math.ceil(avcMw * 1.05),
        tickAmount: 4,
        labels: {
          formatter: (v: number) => v.toFixed(0),
          style: { colors: TOKENS.textMuted, fontSize: "11px" },
        },
        title: { text: "MW", style: { color: TOKENS.textMuted, fontSize: "11px" } },
      },
      tooltip: {
        ...baseOptions.tooltip,
        shared: true,
        intersect: false,
        y: { formatter: (v: number) => (v == null ? "—" : `${v.toFixed(2)} MW`) },
      },
    };

    return { series: s, options: o };
  }, [blocks, optimisedSchedule, avcMw]);

  if (!blocks?.length) {
    return (
      <div className="flex h-[340px] items-center justify-center text-sm text-text-muted">
        No forecast for this window.
      </div>
    );
  }

  return <Chart options={options} series={series} type="rangeArea" height={340} />;
}
