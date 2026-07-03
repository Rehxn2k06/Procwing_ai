/**
 * pages/PortalPage.tsx
 *
 * The single page of the ProcWing Collections Portal.
 *
 * Owns the shared filter state (bucket, search, page) and re-fetches the
 * invoice summary + invoice list whenever any of these change.
 *
 * Component tree:
 *   PortalPage
 *     ├─ UploadPanel          → POST /api/upload; on success calls refreshAll()
 *     ├─ BucketTabs           → renders GET /api/invoices/summary data
 *     ├─ SearchBox            → sets `search` filter (debounced in the component)
 *     └─ InvoiceTable         → renders GET /api/invoices data; owns pagination
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getInvoiceSummary, getInvoices, ApiError } from "../api/client";
import type {
  AgeingBucketSummary,
  BucketFilter,
  InvoiceListResponse,
} from "../api/types";
import BucketTabs from "../components/BucketTabs";
import InvoiceTable from "../components/InvoiceTable";
import SearchBox from "../components/SearchBox";
import UploadPanel from "../components/UploadPanel";
import styles from "./PortalPage.module.css";

const PAGE_SIZE = 50;

export default function PortalPage() {
  // ---------------------------------------------------------------------------
  // Shared filter state
  // ---------------------------------------------------------------------------
  const [activeBucket, setActiveBucket] = useState<BucketFilter>("ALL");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  // ---------------------------------------------------------------------------
  // Summary (bucket tabs) state
  // ---------------------------------------------------------------------------
  const [summaryBuckets, setSummaryBuckets] = useState<AgeingBucketSummary[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // ---------------------------------------------------------------------------
  // Invoice list state
  // ---------------------------------------------------------------------------
  const [invoiceData, setInvoiceData] = useState<InvoiceListResponse | null>(null);
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [invoiceError, setInvoiceError] = useState<string | null>(null);

  // Abort controller ref — cancels in-flight invoice fetches when filters change.
  const abortRef = useRef<AbortController | null>(null);

  // ---------------------------------------------------------------------------
  // Fetch functions
  // ---------------------------------------------------------------------------

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const data = await getInvoiceSummary();
      setSummaryBuckets(data.buckets);
    } catch (err) {
      if (err instanceof ApiError && err.httpStatus === 409) {
        // NO_DATA_UPLOADED — expected before first upload; reset to empty.
        setSummaryBuckets([]);
      }
      // Other errors: silently ignore — the invoice list error state will surface them.
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  const fetchInvoices = useCallback(
    async (bucket: BucketFilter, searchValue: string, pageNum: number) => {
      // Cancel any in-flight request.
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setInvoiceLoading(true);
      setInvoiceError(null);

      try {
        const data = await getInvoices({
          bucket,
          search: searchValue || undefined,
          page: pageNum,
          pageSize: PAGE_SIZE,
        });
        setInvoiceData(data);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.httpStatus === 409) {
            // NO_DATA_UPLOADED — clear the table gracefully.
            setInvoiceData(null);
          } else {
            setInvoiceError(err.message);
          }
        } else {
          setInvoiceError("Unexpected error loading invoices.");
        }
      } finally {
        setInvoiceLoading(false);
      }
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Refresh both summary + invoices (called after a successful upload)
  // ---------------------------------------------------------------------------

  const refreshAll = useCallback(() => {
    void fetchSummary();
    void fetchInvoices(activeBucket, search, 1);
    setPage(1);
  }, [fetchSummary, fetchInvoices, activeBucket, search]);

  // ---------------------------------------------------------------------------
  // Re-fetch invoices when filters change
  // ---------------------------------------------------------------------------

  useEffect(() => {
    void fetchInvoices(activeBucket, search, page);
  }, [fetchInvoices, activeBucket, search, page]);

  // Initial summary load.
  useEffect(() => {
    void fetchSummary();
  }, [fetchSummary]);

  // ---------------------------------------------------------------------------
  // Filter change handlers — all reset to page 1
  // ---------------------------------------------------------------------------

  function handleBucketChange(bucket: BucketFilter) {
    setActiveBucket(bucket);
    setPage(1);
  }

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(1);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className={styles.layout}>
      {/* ── Header ── */}
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}>
            <span className={styles.brandIcon} aria-hidden="true">🦅</span>
            <div>
              <h1 className={styles.brandName}>ProcWing Collections</h1>
              <p className={styles.brandTagline}>AR Ageing Portal</p>
            </div>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className={styles.main}>
        {/* Upload panel */}
        <div className={styles.uploadSection}>
          <UploadPanel onUploadSuccess={refreshAll} />
        </div>

        {/* Dashboard section — only rendered once we have data or are loading */}
        <div className={styles.dashboard}>
          {/* Bucket tabs */}
          <div className={styles.tabsSection}>
            {summaryLoading && summaryBuckets.length === 0 ? (
              <div className={styles.skeletonTabs} aria-busy="true" aria-label="Loading summary…">
                {Array.from({ length: 7 }).map((_, i) => (
                  <div key={i} className={styles.skeletonTab} />
                ))}
              </div>
            ) : summaryBuckets.length > 0 ? (
              <BucketTabs
                buckets={summaryBuckets}
                activeBucket={activeBucket}
                onBucketChange={handleBucketChange}
              />
            ) : (
              <div className={styles.emptyState}>
                <span className={styles.emptyIcon} aria-hidden="true">📋</span>
                <p>Upload an AR sheet above to see invoice data.</p>
              </div>
            )}
          </div>

          {/* Search + table — only show when we have data */}
          {(summaryBuckets.length > 0 || invoiceData !== null) && (
            <>
              <div className={styles.searchRow}>
                <SearchBox value={search} onSearchChange={handleSearchChange} />
              </div>

              <InvoiceTable
                invoices={invoiceData?.items ?? []}
                totalCount={invoiceData?.totalCount ?? 0}
                page={page}
                pageSize={PAGE_SIZE}
                loading={invoiceLoading}
                error={invoiceError}
                activeBucket={activeBucket}
                onPageChange={setPage}
              />
            </>
          )}
        </div>
      </main>

      {/* ── Footer ── */}
      <footer className={styles.footer}>
        <p>ProcWing Collections Portal · AR Ageing &amp; Follow-up Tool</p>
      </footer>
    </div>
  );
}
