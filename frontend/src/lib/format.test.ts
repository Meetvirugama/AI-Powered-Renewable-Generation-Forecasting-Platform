import { expect, test } from "vitest";
import { inr, inrCompact, blockToIST } from "./format";

test("inr formats with Indian digit grouping", () => {
  // Use replace to strip out potential non-breaking spaces before the currency symbol or elsewhere
  expect(inr(1234567).replace(/\s/g, "")).toBe("₹12,34,567");
});

test("inrCompact formats to lakhs", () => {
  // Use replace to strip out potential non-breaking spaces, or native L mapping if needed.
  // Note: Node's Intl compact notation outputs 'T' for thousands on en-IN in some versions,
  // but 'L' for Lakhs and 'Cr' for Crores. We test for standard '₹12.3L' equivalent.
  // Some Node versions output "₹12.3L", some output "₹ 12.3 L", so we strip whitespace to be safe.
  expect(inrCompact(1234567).replace(/\s/g, "")).toBe("₹12.3L");
});

test("blockToIST converts 1-indexed blocks to HH:MM", () => {
  expect(blockToIST(1)).toBe("00:00");
  expect(blockToIST(54)).toBe("13:15");
  expect(blockToIST(96)).toBe("23:45");
});
