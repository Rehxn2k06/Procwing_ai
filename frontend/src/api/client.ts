/**
 * api/client.ts
 *
 * One typed fetch wrapper per endpoint.  All network calls in the app flow
 * through this file — components never call fetch() directly
 * (CODING_STANDARDS.md §2).
 *
 * snake_case → camelCase conversion is centralised in `toCamel` / `deepToCamel`
 * below.  It runs once at the fetch boundary so every type imported from
 * api/types.ts stays clean camelCase throughout the React tree.
 */

import type {
  CollectionFollowupResponse,
  CustomerListResponse,
  CustomerResolveResponse,
  ErrorResponse,
  HealthResponse,
  InvoiceListResponse,
  InvoiceSummaryResponse,
  PaymentScheduleResponse,
  UploadResponse,
  WhatsappPreviewResponse,
  WhatsappPreviewType,
  BucketFilter,
} from "./types";

// ---------------------------------------------------------------------------
// Base URL — centralised here so it's one place to change if needed.
// The Vite dev server proxies /api/* to http://localhost:8000 (vite.config.ts).
// ---------------------------------------------------------------------------

const API_BASE = "/api";

// ---------------------------------------------------------------------------
// Typed API error — thrown on any non-2xx response
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  public readonly errorCode: string;
  public readonly httpStatus: number;

  constructor(errorResponse: ErrorResponse, httpStatus: number) {
    super(errorResponse.message);
    this.name = "ApiError";
    this.errorCode = errorResponse.error;
    this.httpStatus = httpStatus;
  }
}

// ---------------------------------------------------------------------------
// snake_case → camelCase converter (centralised, never repeated per-function)
// ---------------------------------------------------------------------------

/** Convert a single snake_case key to camelCase. */
function toCamel(key: string): string {
  return key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

/** Recursively walk an unknown value, converting all object keys to camelCase. */
function deepToCamel(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(deepToCamel);
  }
  if (value !== null && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      result[toCamel(k)] = deepToCamel(v);
    }
    return result;
  }
  return value;
}

// ---------------------------------------------------------------------------
// Internal fetch helper — performs the request and handles errors uniformly
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    let errorBody: ErrorResponse;
    try {
      const raw = (await response.json()) as Record<string, unknown>;
      errorBody = deepToCamel(raw) as ErrorResponse;
    } catch {
      errorBody = {
        error: "UNKNOWN_ERROR",
        message: `HTTP ${response.status} ${response.statusText}`,
      };
    }
    throw new ApiError(errorBody, response.status);
  }

  const raw = (await response.json()) as unknown;
  return deepToCamel(raw) as T;
}

// ---------------------------------------------------------------------------
// Public API functions — one per endpoint (API_SPEC.md §1–§10)
// ---------------------------------------------------------------------------

/**
 * POST /api/upload
 * Uploads an .xlsx AR sheet.  Replaces the entire in-memory store.
 */
export async function uploadSheet(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  // Note: do NOT set Content-Type header — browser sets it with the boundary.
  return apiFetch<UploadResponse>("/upload", {
    method: "POST",
    body: formData,
    headers: {},
  });
}

/**
 * GET /api/invoices/summary
 * Returns bucket-level counts and totals for the tab row.
 */
export async function getInvoiceSummary(): Promise<InvoiceSummaryResponse> {
  return apiFetch<InvoiceSummaryResponse>("/invoices/summary");
}

/**
 * GET /api/invoices
 * Filtered, paginated invoice list powering the table under the tabs.
 */
export async function getInvoices(params: {
  bucket?: BucketFilter;
  search?: string;
  page?: number;
  pageSize?: number;
}): Promise<InvoiceListResponse> {
  const qs = new URLSearchParams();
  if (params.bucket && params.bucket !== "ALL") {
    qs.set("bucket", params.bucket);
  }
  if (params.search) {
    qs.set("search", params.search);
  }
  if (params.page !== undefined) {
    qs.set("page", String(params.page));
  }
  if (params.pageSize !== undefined) {
    qs.set("page_size", String(params.pageSize));
  }
  const query = qs.toString();
  return apiFetch<InvoiceListResponse>(`/invoices${query ? `?${query}` : ""}`);
}

/**
 * GET /api/customers
 * List of distinct customers for dropdowns and lookups.
 */
export async function getCustomers(): Promise<CustomerListResponse> {
  return apiFetch<CustomerListResponse>("/customers");
}

/**
 * GET /api/customers/resolve?query=...
 * Fuzzy-resolves free text to a customer_key.
 */
export async function resolveCustomer(
  query: string
): Promise<CustomerResolveResponse> {
  const qs = new URLSearchParams({ query });
  return apiFetch<CustomerResolveResponse>(`/customers/resolve?${qs}`);
}

/**
 * GET /api/customers/{customer_key}/payment-schedule
 * Structured payment-schedule data for a single customer.
 */
export async function getPaymentSchedule(
  customerKey: string
): Promise<PaymentScheduleResponse> {
  return apiFetch<PaymentScheduleResponse>(
    `/customers/${encodeURIComponent(customerKey)}/payment-schedule`
  );
}

/**
 * GET /api/customers/{customer_key}/collection-followup
 * Structured collection-followup data for a single customer.
 */
export async function getCollectionFollowup(
  customerKey: string
): Promise<CollectionFollowupResponse> {
  return apiFetch<CollectionFollowupResponse>(
    `/customers/${encodeURIComponent(customerKey)}/collection-followup`
  );
}

/**
 * GET /api/customers/{customer_key}/whatsapp-preview?type=...
 * Returns the exact rendered WhatsApp text for a customer report.
 */
export async function getWhatsappPreview(
  customerKey: string,
  type: WhatsappPreviewType
): Promise<WhatsappPreviewResponse> {
  const qs = new URLSearchParams({ type });
  return apiFetch<WhatsappPreviewResponse>(
    `/customers/${encodeURIComponent(customerKey)}/whatsapp-preview?${qs}`
  );
}

/**
 * GET /api/health
 * Confirms the backend is up and how many invoices are loaded.
 */
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}
