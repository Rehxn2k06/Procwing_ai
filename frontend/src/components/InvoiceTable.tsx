/**
 * components/InvoiceTable.tsx
 *
 * Renders the paginated invoice list for the active bucket + search filters.
 * Columns: Customer, SPOC, Invoice No, Due Date, Outstanding, Ageing Bucket.
 *
 * Pagination uses prev/next page buttons driven by totalCount / pageSize from
 * the InvoiceListResponse (API_SPEC.md §3).
 *
 * Loading, empty, and error states are all handled.
 *
 * Includes an optional "Preview" popover for payment schedule and collection
 * followup messages (nice-to-have — AGENT_PROMPT_FRONTEND.md §"Explicitly not
 * your job" allows it as optional).
 */

import { useEffect, useState } from "react";
import type { Invoice, BucketFilter } from "../api/types";
import { getWhatsappPreview, ApiError } from "../api/client";
import { formatINR } from "../utils/formatCurrency";
import styles from "./InvoiceTable.module.css";

interface InvoiceTableProps {
  invoices: Invoice[];
  totalCount: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  activeBucket: BucketFilter;
  onPageChange: (page: number) => void;
}

/** Human-readable labels for ageing buckets in table cells. */
const BUCKET_DISPLAY: Record<string, string> = {
  NOT_DUE: "Not Due",
  "0-15": "0–15 d",
  "16-30": "16–30 d",
  "31-60": "31–60 d",
  "61-90": "61–90 d",
  "90+": "90+ d",
  NO_DUE_DATE: "No Due Date",
};

/** Map bucket value to a CSS modifier class name. */
function bucketClass(bucket: string): string {
  const map: Record<string, string> = {
    NOT_DUE: styles.badgeNotDue,
    "0-15": styles.badge015,
    "16-30": styles.badge1630,
    "31-60": styles.badge3160,
    "61-90": styles.badge6190,
    "90+": styles.badge90plus,
    NO_DUE_DATE: styles.badgeNoDue,
  };
  return map[bucket] ?? "";
}

// ---------------------------------------------------------------------------
// Preview modal (optional nice-to-have: shows WhatsApp preview text)
// ---------------------------------------------------------------------------

interface PreviewModalProps {
  customerKey: string;
  displayName: string;
  onClose: () => void;
}

function PreviewModal({ customerKey, displayName, onClose }: PreviewModalProps) {
  const [activeTab, setActiveTab] = useState<"payment_schedule" | "collection_followup">(
    "payment_schedule"
  );
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPreview(type: "payment_schedule" | "collection_followup") {
    setActiveTab(type);
    setPreviewText(null);
    setError(null);
    setLoading(true);
    try {
      const res = await getWhatsappPreview(customerKey, type);
      setPreviewText(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load preview.");
    } finally {
      setLoading(false);
    }
  }

  // Load on first render using useEffect (the correct hook for side effects).
  useEffect(() => {
    void loadPreview("payment_schedule");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerKey]);

  return (
    <div className={styles.modalBackdrop} role="dialog" aria-modal="true" aria-label={`Preview for ${displayName}`}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>WhatsApp Preview — {displayName}</h3>
          <button className={styles.modalClose} onClick={onClose} aria-label="Close preview">✕</button>
        </div>
        <div className={styles.modalTabs}>
          <button
            className={`${styles.modalTab} ${activeTab === "payment_schedule" ? styles.modalTabActive : ""}`}
            onClick={() => void loadPreview("payment_schedule")}
          >
            Payment Schedule
          </button>
          <button
            className={`${styles.modalTab} ${activeTab === "collection_followup" ? styles.modalTabActive : ""}`}
            onClick={() => void loadPreview("collection_followup")}
          >
            Collection Follow-up
          </button>
        </div>
        <div className={styles.modalBody}>
          {loading && <span className="spinner" aria-label="Loading…" />}
          {error && <div className="alert alert-error"><span className="alert-icon">✕</span>{error}</div>}
          {previewText && !loading && (
            <pre className={styles.previewText}>{previewText}</pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main table component
// ---------------------------------------------------------------------------

export default function InvoiceTable({
  invoices,
  totalCount,
  page,
  pageSize,
  loading,
  error,
  activeBucket,
  onPageChange,
}: InvoiceTableProps) {
  const [previewTarget, setPreviewTarget] = useState<{
    customerKey: string;
    displayName: string;
  } | null>(null);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const start = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalCount);

  return (
    <section
      id="invoice-table-panel"
      role="tabpanel"
      aria-label={`Invoices — ${activeBucket}`}
      className={styles.section}
    >
      {/* Row count / status bar */}
      <div className={styles.statusBar}>
        <span className={styles.countText}>
          {loading
            ? "Loading…"
            : totalCount === 0
            ? "No invoices found"
            : `Showing ${start}–${end} of ${totalCount} invoice${totalCount !== 1 ? "s" : ""}`}
        </span>
        {loading && <span className="spinner" aria-hidden="true" />}
      </div>

      {/* Error state */}
      {error && (
        <div className="alert alert-error" role="alert">
          <span className="alert-icon">✕</span>
          {error}
        </div>
      )}

      {/* Table */}
      <div className={styles.tableWrapper}>
        <table className={styles.table} aria-busy={loading}>
          <thead>
            <tr>
              <th scope="col">Customer</th>
              <th scope="col">SPOC</th>
              <th scope="col">Invoice No</th>
              <th scope="col">Due Date</th>
              <th scope="col" className={styles.numberCol}>Outstanding</th>
              <th scope="col">Ageing</th>
              <th scope="col" className={styles.actionCol}>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 && !loading && (
              <tr>
                <td colSpan={7} className={styles.emptyCell}>
                  No invoices match the current filters.
                </td>
              </tr>
            )}
            {invoices.map((inv) => (
              <tr key={inv.id} className={inv.isDueThisWeek ? styles.dueThisWeek : undefined}>
                <td className={styles.customerCell} title={inv.customerRaw}>
                  {inv.customerRaw}
                </td>
                <td className={styles.spocCell}>{inv.spoc ?? "—"}</td>
                <td className={styles.monoCell}>{inv.invoiceNo}</td>
                <td className={styles.dateCell}>
                  {inv.dueDate ?? <span className={styles.muted}>—</span>}
                </td>
                <td className={styles.numberCol}>
                  {formatINR(inv.outstanding)}
                </td>
                <td>
                  <span className={`${styles.badge} ${bucketClass(inv.ageingBucket)}`}>
                    {BUCKET_DISPLAY[inv.ageingBucket] ?? inv.ageingBucket}
                  </span>
                </td>
                <td className={styles.actionCol}>
                  <button
                    type="button"
                    className={styles.previewBtn}
                    onClick={() =>
                      setPreviewTarget({
                        customerKey: inv.customerKey,
                        displayName: inv.customerRaw,
                      })
                    }
                    aria-label={`Preview WhatsApp messages for ${inv.customerRaw}`}
                    title="WhatsApp preview"
                  >
                    💬
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className={styles.pagination}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1 || loading}
            aria-label="Previous page"
          >
            ← Prev
          </button>
          <span className={styles.pageInfo}>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages || loading}
            aria-label="Next page"
          >
            Next →
          </button>
        </div>
      )}

      {/* WhatsApp preview modal */}
      {previewTarget && (
        <PreviewModal
          customerKey={previewTarget.customerKey}
          displayName={previewTarget.displayName}
          onClose={() => setPreviewTarget(null)}
        />
      )}
    </section>
  );
}
