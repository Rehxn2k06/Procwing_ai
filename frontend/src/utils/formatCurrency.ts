/**
 * utils/formatCurrency.ts
 *
 * Indian Rupee formatter with Indian digit grouping (e.g. ₹1,23,456).
 * Written once here — never inlined in components or duplicated elsewhere
 * (API_SPEC.md §0: "formatting happens only in Frontend/WhatsApp render layers").
 *
 * Indian grouping rules:
 *   - Last three digits before the decimal form the first group.
 *   - Subsequent groups to the left are two digits each.
 *   Example: 1234567.89 → ₹12,34,567.89
 */

/**
 * Format a number as Indian Rupees with the ₹ prefix.
 *
 * @param amount - Numeric value in INR (no currency symbol in API payloads).
 * @param decimals - Number of decimal places to show (default 2).
 * @returns Formatted string, e.g. "₹1,23,456.00"
 */
export function formatINR(amount: number, decimals = 2): string {
  // Handle negative amounts: format the absolute value, then re-apply the sign.
  const isNegative = amount < 0;
  const abs = Math.abs(amount);

  // Split into integer and fractional parts.
  const fixed = abs.toFixed(decimals);
  const [intPart, fracPart] = fixed.split(".");

  // Apply Indian grouping to the integer part.
  const grouped = applyIndianGrouping(intPart ?? "0");

  const formatted =
    decimals > 0 ? `${grouped}.${fracPart ?? "00"}` : grouped;

  return `${isNegative ? "-" : ""}₹${formatted}`;
}

/**
 * Apply Indian digit grouping to the integer-part string.
 * Last 3 digits are one group; every subsequent pair (going left) is a group.
 */
function applyIndianGrouping(intStr: string): string {
  if (intStr.length <= 3) {
    return intStr;
  }

  // The rightmost 3 digits.
  const lastThree = intStr.slice(-3);
  // Everything to the left.
  const remaining = intStr.slice(0, intStr.length - 3);

  // Split remaining into 2-digit groups from the right.
  const groups: string[] = [];
  let i = remaining.length;
  while (i > 0) {
    const start = Math.max(0, i - 2);
    groups.unshift(remaining.slice(start, i));
    i = start;
  }

  return `${groups.join(",")},${lastThree}`;
}

/**
 * Compact formatter for totals that may be very large.
 * Falls back to full formatting for numbers below 1 lakh.
 *
 * @param amount - Numeric value in INR.
 * @returns e.g. "₹12.3 Cr", "₹4.5 L", "₹1,234.00"
 */
export function formatINRCompact(amount: number): string {
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";

  if (abs >= 1_00_00_000) {
    // 1 crore = 1,00,00,000
    return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  }
  if (abs >= 1_00_000) {
    // 1 lakh = 1,00,000
    return `${sign}₹${(abs / 1_00_000).toFixed(2)} L`;
  }
  return formatINR(amount);
}
