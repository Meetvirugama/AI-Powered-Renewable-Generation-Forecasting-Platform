// Formatters are module-scope singletons: RiskHeatmap's tooltip calls inr() on every
// pointer move across 96 cells, and rebuilding Intl.NumberFormat each time re-pays
// locale/currency resolution for nothing.

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const INR_COMPACT = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** ₹12,34,567 — Indian digit grouping, not the Western 1,234,567. */
export const inr = (value: number): string => INR.format(value);

/** ₹12.3L · ₹1.2Cr — for axis ticks and stat tiles, never tooltips. */
export const inrCompact = (value: number): string => INR_COMPACT.format(value);

/**
 * A savings amount (always >= 0) framed as a reduction, e.g. "−₹10,146".
 *
 * The previous version prefixed a literal "−" onto inr(value) unconditionally, which
 * rendered a neutral zero as "−₹0". Negating the number and letting Intl supply its
 * own sign has the same failure by a different route: `-0 === 0` numerically, but
 * Intl.NumberFormat renders negative zero as "-0" — so this checks the sign explicitly
 * rather than ever constructing -0.
 */
export const inrSaved = (value: number): string =>
  value > 0 ? `−${INR.format(value)}` : INR.format(value);

/**
 * Block numbers are 1-indexed (1..96), 15 minutes apart, starting 00:00 IST.
 * The single source of truth for this conversion — apexTheme re-exports it rather
 * than reimplementing the arithmetic.
 */
export const blockToIST = (blockNo: number): string => {
  const totalMinutes = (blockNo - 1) * 15;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}`;
};

/** Inverse of blockToIST: which 1-indexed block covers this hour and minute offset. */
export const blockNoFor = (hour: number, minuteOffset: number): number =>
  hour * 4 + minuteOffset / 15 + 1;

/**
 * Today's date in IST as YYYY-MM-DD.
 *
 * `new Date().toISOString()` yields the UTC date, which is the previous day between
 * 00:00 and 05:29 IST — long enough to make an operator's first morning load query
 * yesterday's schedule. Every date this app sends to the backend is an IST calendar
 * date, so it must be computed in IST.
 */
export const todayIST = (): string => {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
};

/** Wall-clock time in IST, for the live status rail. */
export const nowIST = (): string =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date());

/**
 * CERC deviation tolerance band by asset type. Solar and wind differ (10% vs 15% under
 * the 2026 rules), so no screen may hardcode one and label it generically.
 * Mirrors config/dsm_rules_*.yaml.
 */
export const getToleranceBand = (
  plantType: string | undefined
): { fraction: number; label: string } =>
  plantType === "wind"
    ? { fraction: 0.15, label: "Wind band ±15%" }
    : { fraction: 0.1, label: "Solar band ±10%" };

/** "solar" -> "Solar". Single source for the display label of a plant type. */
export const plantTypeLabel = (plantType: string | undefined): string =>
  plantType === "wind" ? "Wind" : "Solar";
