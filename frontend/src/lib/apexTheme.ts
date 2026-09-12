import type { ApexOptions } from "apexcharts";
import { blockToIST } from "./format";

// Shared ApexCharts defaults. Every chart in the app spreads these first, so the dark
// ground, token colours and tabular figures are set in exactly one place.

export const TOKENS = {
  bg: "#0B0F0E",
  surface: "#131917",
  surface2: "#1B2321",
  border: "#2A3330",
  text: "#E9EFEC",
  textMuted: "#93A29C",
  accent: "#CFF245",
  pen: ["#1B2321", "#402030", "#6B2A44", "#9C3355", "#CE3C63", "#FF5C7A"],
  devUnder: "#6EA8FF",
  devZero: "#2A3330",
  devOver: "#FF9F45",
  solar: "#F5B33C",
  wind: "#5EC8C8",
} as const;

/**
 * Re-exported so chart code has one import path for chart concerns, but the actual
 * block->HH:MM arithmetic lives in lib/format.ts exactly once. This used to be a
 * second, independent implementation of the same formula.
 */
export const blockLabel = blockToIST;

export const baseOptions: ApexOptions = {
  chart: {
    background: "transparent",
    foreColor: TOKENS.textMuted,
    toolbar: { show: false },
    zoom: { enabled: false },
    fontFamily: "Inter, system-ui, sans-serif",
    animations: { enabled: true, speed: 300 },
  },
  theme: { mode: "dark" },
  grid: {
    borderColor: TOKENS.border,
    strokeDashArray: 0,
    xaxis: { lines: { show: false } },
    yaxis: { lines: { show: true } },
    padding: { left: 4, right: 8, top: 0, bottom: 0 },
  },
  dataLabels: { enabled: false },
  tooltip: {
    theme: "dark",
    style: { fontSize: "12px", fontFamily: "Inter, system-ui, sans-serif" },
  },
  legend: {
    show: true,
    position: "top",
    horizontalAlign: "right",
    fontSize: "12px",
    labels: { colors: TOKENS.textMuted },
    markers: { size: 6 },
    itemMargin: { horizontal: 8 },
  },
  stroke: { curve: "smooth", width: 2 },
  states: {
    hover: { filter: { type: "none" } },
    active: { filter: { type: "none" } },
  },
};

/** Category axis of 96 IST labels, thinned so ticks stay legible. */
export const istCategories = (): string[] =>
  Array.from({ length: 96 }, (_, i) => blockLabel(i + 1));
