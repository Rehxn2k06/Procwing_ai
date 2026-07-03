/**
 * components/UploadPanel.tsx
 *
 * File input restricted to .xlsx.  Calls POST /api/upload (multipart) via
 * api/client.ts#uploadSheet.  Shows:
 *   - Success: customer count, invoice count, total outstanding, any warnings.
 *   - Error: the ErrorResponse.message from the API.
 *
 * On success, calls props.onUploadSuccess() so PortalPage refreshes the summary
 * and invoice list.
 */

import { useRef, useState } from "react";
import { uploadSheet, ApiError } from "../api/client";
import type { UploadResponse } from "../api/types";
import { formatINR } from "../utils/formatCurrency";
import styles from "./UploadPanel.module.css";

interface UploadPanelProps {
  onUploadSuccess: () => void;
}

type UploadState =
  | { status: "idle" }
  | { status: "uploading" }
  | { status: "success"; data: UploadResponse }
  | { status: "error"; message: string };

export default function UploadPanel({ onUploadSuccess }: UploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>({ status: "idle" });
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    if (!file.name.endsWith(".xlsx")) {
      setState({
        status: "error",
        message: "Only .xlsx files are accepted. Please select a valid Excel file.",
      });
      return;
    }

    setState({ status: "uploading" });
    try {
      const data = await uploadSheet(file);
      setState({ status: "success", data });
      onUploadSuccess();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Unexpected error during upload. Please try again.";
      setState({ status: "error", message });
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
    // Reset the input value so the same file can be re-uploaded if needed.
    e.target.value = "";
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave() {
    setDragOver(false);
  }

  const isUploading = state.status === "uploading";

  return (
    <section className={styles.panel} aria-label="Upload AR Sheet">
      <h2 className={styles.heading}>Upload AR Sheet</h2>

      <div
        className={`${styles.dropzone} ${dragOver ? styles.dragOver : ""} ${isUploading ? styles.disabled : ""}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="button"
        tabIndex={0}
        aria-disabled={isUploading}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !isUploading) {
            fileInputRef.current?.click();
          }
        }}
      >
        <input
          ref={fileInputRef}
          id="upload-file-input"
          type="file"
          accept=".xlsx"
          className="sr-only"
          onChange={handleInputChange}
          disabled={isUploading}
          aria-label="Select .xlsx file to upload"
        />

        {isUploading ? (
          <>
            <span className="spinner" aria-hidden="true" />
            <span className={styles.dropText}>Uploading…</span>
          </>
        ) : (
          <>
            <span className={styles.dropIcon} aria-hidden="true">📂</span>
            <span className={styles.dropText}>
              Drag &amp; drop an <strong>.xlsx</strong> file here, or{" "}
              <span className={styles.browseLink}>click to browse</span>
            </span>
            <span className={styles.dropHint}>
              Required columns: Customer, SPOC, Invoice No, Invoice Date, Due Date,
              Inv Amount, Received, Outstanding
            </span>
          </>
        )}
      </div>

      {state.status === "success" && (
        <div className="alert alert-success" role="status">
          <span className="alert-icon">✓</span>
          <div>
            <strong>Upload successful.</strong> Loaded{" "}
            <strong>{state.data.invoicesCount}</strong> invoice
            {state.data.invoicesCount !== 1 ? "s" : ""} across{" "}
            <strong>{state.data.customersCount}</strong> customer
            {state.data.customersCount !== 1 ? "s" : ""}.
            Total outstanding: <strong>{formatINR(state.data.totalOutstanding)}</strong>.
            {state.data.warnings.length > 0 && (
              <ul className={styles.warningList}>
                {state.data.warnings.map((w) => (
                  <li key={`${w.row}-${w.invoiceNo}`}>
                    Row {w.row} — {w.invoiceNo}: {w.issue}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {state.status === "error" && (
        <div className="alert alert-error" role="alert">
          <span className="alert-icon">✕</span>
          <div>
            <strong>Upload failed.</strong> {state.message}
          </div>
        </div>
      )}
    </section>
  );
}
