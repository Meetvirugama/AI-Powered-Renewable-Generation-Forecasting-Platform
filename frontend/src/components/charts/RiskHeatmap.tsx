import { useMemo } from "react";
import Chart from "react-apexcharts";
import type { ApexOptions } from "apexcharts";
import { BlockDSMResult } from "../../types/api";
import { baseOptions, TOKENS } from "../../lib/apexTheme";
import { inr, blockToIST, blockNoFor } from "../../lib/format";

interface Props {
  blocks: BlockDSMResult[];
}

/**
 * 96 blocks as 4 rows (15-min offset) x 24 columns (hour IST).
 * Rose sequential ramp: on a dark ground, brighter means worse. Ramping toward dark
 * would hide the costliest blocks in the background.
 */
export default function RiskHeatmap({ blocks }: Props) {
  const { series, options } = useMemo(() => {
    const byBlock = new Map(blocks.map((b) => [b.block_no, b]));
    const max = blocks.reduce((m, b) => Math.max(m, b.expected_penalty_inr), 0) || 1;

    // Row 0 = :00, row 1 = :15, row 2 = :30, row 3 = :45. Rendered bottom-up by Apex,
    // so build in reverse to keep :00 at the top.
    const rows = [45, 30, 15, 0].map((offset) => ({
      name: `:${String(offset).padStart(2, "0")}`,
      data: Array.from({ length: 24 }, (_, hour) => {
        const blockNo = blockNoFor(hour, offset);
        return {
          x: String(hour).padStart(2, "0"),
          y: Number((byBlock.get(blockNo)?.expected_penalty_inr ?? 0).toFixed(2)),
        };
      }),
    }));

    const step = max / 5;
    const o: ApexOptions = {
      ...baseOptions,
      chart: { ...baseOptions.chart, type: "heatmap", height: 200 },
      legend: { show: false },
      stroke: { show: false },
      plotOptions: {
        heatmap: {
          radius: 3,
          enableShades: false,
          colorScale: {
            ranges: TOKENS.pen.map((color, i) => ({
              from: i === 0 ? -1 : step * i,
              to: i === 5 ? max * 1.01 : step * (i + 1),
              color,
              name:
                i === 0
                  ? "None"
                  : `${inr(step * i)}+`,
            })),
          },
        },
      },
      xaxis: {
        type: "category",
        labels: { style: { colors: TOKENS.textMuted, fontSize: "11px" } },
        axisBorder: { color: TOKENS.border },
        axisTicks: { color: TOKENS.border },
        title: { text: "Hour (IST)", style: { color: TOKENS.textMuted, fontSize: "11px" } },
      },
      yaxis: {
        labels: { style: { colors: TOKENS.textMuted, fontSize: "11px" } },
      },
      tooltip: {
        ...baseOptions.tooltip,
        fixed: { enabled: true, position: 'topLeft', offsetX: 0, offsetY: 0 },
        // Colour is never the only signal — the tooltip always names the value.
        custom: ({ seriesIndex, dataPointIndex, w }) => {
          const offset = [45, 30, 15, 0][seriesIndex];
          const hour = dataPointIndex;
          const blockNo = blockNoFor(hour, offset);
          const b = byBlock.get(blockNo);
          const t = blockToIST(blockNo);
          void w;
          return `<div style="padding:8px 10px;font-family:Inter,sans-serif;font-size:12px">
            <div style="color:${TOKENS.textMuted}">Block ${blockNo} · ${t} IST</div>
            <div style="color:${TOKENS.text};font-weight:600;margin-top:3px">
              ${inr(b?.expected_penalty_inr ?? 0)}
            </div>
            <div style="color:${TOKENS.textMuted};margin-top:2px">
              Deviation ${(b?.deviation_pct_at_p50 ?? 0).toFixed(1)}% ·
              Sched ${(b?.schedule_mw ?? 0).toFixed(1)} MW
            </div>
          </div>`;
        },
      },
    };

    return { series: rows, options: o };
  }, [blocks]);

  if (!blocks?.length) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-text-muted">
        No deviation penalty in this window.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[560px] pb-6">
        <Chart options={options} series={series} type="heatmap" height={200} />
      </div>
    </div>
  );
}
