/**
 * components/BucketTabs.tsx
 *
 * Renders one card-style tab per bucket returned by GET /api/invoices/summary.
 * Tab order: All → Not Due → 0-15 → 16-30 → 31-60 → 61-90 → 90+ → No Due Date.
 * NO_DUE_DATE is shown only when its count > 0 (API_SPEC.md §2).
 *
 * Each tab shows:
 *   - Bucket label
 *   - Invoice count
 *   - Total outstanding (₹ Indian format, compact for large numbers)
 *
 * Selecting a tab calls props.onBucketChange with the new BucketFilter.
 */

import type { AgeingBucketSummary, BucketFilter } from "../api/types";
import { formatINRCompact } from "../utils/formatCurrency";
import styles from "./BucketTabs.module.css";

interface BucketTabsProps {
  buckets: AgeingBucketSummary[];
  activeBucket: BucketFilter;
  onBucketChange: (bucket: BucketFilter) => void;
}

/** Human-readable labels for each bucket value. */
const BUCKET_LABELS: Record<string, string> = {
  ALL: "All",
  NOT_DUE: "Not Due",
  "0-15": "0–15 Days",
  "16-30": "16–30 Days",
  "31-60": "31–60 Days",
  "61-90": "61–90 Days",
  "90+": "90+ Days",
  NO_DUE_DATE: "No Due Date",
};

/** Display order for the tabs (API_SPEC.md §2). */
const BUCKET_ORDER: BucketFilter[] = [
  "ALL",
  "NOT_DUE",
  "0-15",
  "16-30",
  "31-60",
  "61-90",
  "90+",
  "NO_DUE_DATE",
];

export default function BucketTabs({
  buckets,
  activeBucket,
  onBucketChange,
}: BucketTabsProps) {
  // Index buckets by their bucket key for O(1) lookup.
  const bucketMap = new Map(buckets.map((b) => [b.bucket, b]));

  // Build the ordered list; skip NO_DUE_DATE if its count is 0.
  const visibleBuckets = BUCKET_ORDER.filter((key) => {
    if (key === "NO_DUE_DATE") {
      return (bucketMap.get("NO_DUE_DATE")?.count ?? 0) > 0;
    }
    return bucketMap.has(key);
  });

  return (
    <nav className={styles.nav} aria-label="Ageing bucket tabs">
      <div className={styles.tabList} role="tablist">
        {visibleBuckets.map((bucketKey) => {
          const summary = bucketMap.get(bucketKey);
          const isActive = activeBucket === bucketKey;

          return (
            <button
              key={bucketKey}
              id={`tab-${bucketKey}`}
              role="tab"
              aria-selected={isActive}
              aria-controls="invoice-table-panel"
              className={`${styles.tab} ${isActive ? styles.active : ""} ${styles[`bucket-${bucketKey.replace("+", "plus").replace(/[^a-zA-Z0-9-]/g, "-")}`] ?? ""}`}
              onClick={() => onBucketChange(bucketKey)}
            >
              <span className={styles.label}>{BUCKET_LABELS[bucketKey] ?? bucketKey}</span>
              <span className={styles.count}>
                {summary?.count ?? 0}
                {" "}
                <span className={styles.countLabel}>inv</span>
              </span>
              <span className={styles.total}>
                {formatINRCompact(summary?.totalOutstanding ?? 0)}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
