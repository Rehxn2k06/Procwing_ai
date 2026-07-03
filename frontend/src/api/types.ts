/**
 * api/types.ts
 *
 * Hand-transcribed TypeScript interfaces from API_SPEC.md §0.
 * All field names are camelCase — the snake_case→camelCase conversion happens
 * exclusively in api/client.ts at the fetch boundary.
 * Components never import snake_case shapes.
 */

// ---------------------------------------------------------------------------
// Shared / primitive types
// ---------------------------------------------------------------------------

export type AgeingBucket =
  | "NOT_DUE"
  | "0-15"
  | "16-30"
  | "31-60"
  | "61-90"
  | "90+"
  | "NO_DUE_DATE";

/** ALL is a UI-only filter value, not a real ageing bucket in the Invoice type. */
export type BucketFilter = AgeingBucket | "ALL";

// ---------------------------------------------------------------------------
// Invoice (API_SPEC.md §0 — Invoice)
// ---------------------------------------------------------------------------

export interface Invoice {
  id: string;
  customerRaw: string;
  customerKey: string;
  spoc: string | null;
  invoiceNo: string;
  invoiceDate: string | null;
  dueDate: string | null;
  invAmount: number;
  received: number;
  outstanding: number;
  ageingBucket: AgeingBucket;
  daysOverdue: number | null;
  isDueThisWeek: boolean;
}

// ---------------------------------------------------------------------------
// ErrorResponse (API_SPEC.md §0 — ErrorResponse)
// ---------------------------------------------------------------------------

export interface ErrorResponse {
  error: string;
  message: string;
}

// ---------------------------------------------------------------------------
// POST /api/upload (API_SPEC.md §1)
// ---------------------------------------------------------------------------

export interface UploadWarning {
  row: number;
  invoiceNo: string;
  issue: string;
}

export interface UploadResponse {
  customersCount: number;
  invoicesCount: number;
  totalOutstanding: number;
  warnings: UploadWarning[];
}

// ---------------------------------------------------------------------------
// GET /api/invoices/summary (API_SPEC.md §2)
// ---------------------------------------------------------------------------

export interface AgeingBucketSummary {
  bucket: BucketFilter;
  count: number;
  totalOutstanding: number;
}

export interface InvoiceSummaryResponse {
  buckets: AgeingBucketSummary[];
}

// ---------------------------------------------------------------------------
// GET /api/invoices (API_SPEC.md §3)
// ---------------------------------------------------------------------------

export interface InvoiceListResponse {
  items: Invoice[];
  totalCount: number;
  page: number;
  pageSize: number;
}

// ---------------------------------------------------------------------------
// GET /api/customers (API_SPEC.md §4)
// ---------------------------------------------------------------------------

export interface CustomerInfo {
  customerKey: string;
  displayName: string;
  spoc: string | null;
}

export interface CustomerListResponse {
  customers: CustomerInfo[];
}

// ---------------------------------------------------------------------------
// GET /api/customers/resolve (API_SPEC.md §5)
// ---------------------------------------------------------------------------

export interface CandidateMatch {
  customerKey: string;
  displayName: string;
  confidence: number;
}

export interface CustomerResolveResponse {
  matched: boolean;
  customerKey: string | null;
  displayName: string | null;
  confidence: number;
  candidates: CandidateMatch[];
}

// ---------------------------------------------------------------------------
// GET /api/customers/{key}/payment-schedule (API_SPEC.md §6)
// ---------------------------------------------------------------------------

export interface PaymentScheduleInvoice {
  invoiceNo: string;
  dueDate: string | null;
  outstanding: number;
}

export interface AgeingBreakdown {
  "90+": number;
  "61-90": number;
  "31-60": number;
  "16-30": number;
  "0-15": number;
  overdue: number;
}

export interface PaymentScheduleResponse {
  customerKey: string;
  displayName: string;
  spoc: string | null;
  overdueAmount: number;
  dueThisWeek: number;
  totalOutstanding: number;
  ageingBreakdown: AgeingBreakdown;
  invoices: PaymentScheduleInvoice[];
  noDueDateCount: number;
  noDueDateTotal: number;
}

// ---------------------------------------------------------------------------
// GET /api/customers/{key}/collection-followup (API_SPEC.md §7)
// ---------------------------------------------------------------------------

export interface DailyBreakdownEntry {
  label: string;
  date: string | null;
  amount: number;
}

export interface CollectionFollowupResponse {
  customerKey: string;
  displayName: string;
  spoc: string | null;
  overdueAmount: number;
  dueThisWeek: number;
  weekStart: string;
  weekEnd: string;
  totalCollectionTarget: number;
  dailyBreakdown: DailyBreakdownEntry[];
  invoices: PaymentScheduleInvoice[];
}

// ---------------------------------------------------------------------------
// GET /api/customers/{key}/whatsapp-preview (API_SPEC.md §8)
// ---------------------------------------------------------------------------

export type WhatsappPreviewType = "payment_schedule" | "collection_followup";

export interface WhatsappPreviewResponse {
  message: string;
}

// ---------------------------------------------------------------------------
// GET /api/health (API_SPEC.md §10)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  invoicesLoaded: number;
}
