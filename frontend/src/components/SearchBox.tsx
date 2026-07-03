/**
 * components/SearchBox.tsx
 *
 * Debounced (~300 ms) text input that sets the `search` query parameter via
 * props.onSearchChange, which PortalPage passes down to GET /api/invoices.
 *
 * Search covers customer name and invoice number.
 * NOTE: The original brief also mentions "PO" as a searchable field.
 * The provided sheet has no PO column, so `search` covers only customer_raw
 * and invoice_no — this is a documented gap (API_SPEC.md §3, not a bug).
 */

import { useEffect, useRef, useState } from "react";
import styles from "./SearchBox.module.css";

interface SearchBoxProps {
  value: string;
  onSearchChange: (value: string) => void;
  placeholder?: string;
}

const DEBOUNCE_MS = 300;

export default function SearchBox({
  value,
  onSearchChange,
  placeholder = "Search by customer name or invoice number…",
}: SearchBoxProps) {
  // Local state for the raw (un-debounced) input value.
  const [inputValue, setInputValue] = useState(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep local input in sync when the parent resets the value externally.
  useEffect(() => {
    setInputValue(value);
  }, [value]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.value;
    setInputValue(next);

    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      onSearchChange(next);
    }, DEBOUNCE_MS);
  }

  function handleClear() {
    setInputValue("");
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    onSearchChange("");
  }

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div className={styles.wrapper}>
      <span className={styles.icon} aria-hidden="true">🔍</span>
      <input
        id="invoice-search-input"
        type="search"
        className={styles.input}
        value={inputValue}
        onChange={handleChange}
        placeholder={placeholder}
        aria-label="Search invoices"
        autoComplete="off"
        spellCheck={false}
      />
      {inputValue.length > 0 && (
        <button
          type="button"
          className={styles.clearBtn}
          onClick={handleClear}
          aria-label="Clear search"
        >
          ✕
        </button>
      )}
    </div>
  );
}
