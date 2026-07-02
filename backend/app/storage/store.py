"""backend/app/storage/store.py — In-memory JSON store with thread-safe writes."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom storage exceptions (internal — not exposed as HTTP errors directly)
# ---------------------------------------------------------------------------


class StorageError(Exception):
    """Base class for storage-layer errors."""


class FileSaveError(StorageError):
    """Raised when the atomic write to store.json fails."""


# ---------------------------------------------------------------------------
# Store singleton
# ---------------------------------------------------------------------------

_EMPTY_STORE: dict[str, Any] = {
    "uploaded_at": None,
    "source_filename": None,
    "invoices": [],
}


class Store:
    """Singleton in-memory store backed by data/store.json.

    Thread-safety: a single in-process ``threading.Lock`` guards all writes.
    Reads are lock-free because uvicorn is run with a single worker for this
    assignment (documented assumption in README).
    """

    _instance: Store | None = None
    _creation_lock: threading.Lock = threading.Lock()
    _write_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        if Store._instance is not None:
            raise RuntimeError("Use Store.get_instance() — do not instantiate directly.")
        self._store_file: Path = settings.STORE_FILE
        self._data: dict[str, Any] = dict(_EMPTY_STORE)
        self._data["invoices"] = []
        self.is_loaded: bool = False
        self._store_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Singleton accessor
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> Store:
        """Return the singleton Store instance, creating it if necessary."""
        if cls._instance is None:
            with cls._creation_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_store(self) -> None:
        """Load store.json into memory.

        If the file is absent or empty the store is initialised as empty
        (not an error — the app must start cleanly before any upload).
        Called once at application startup via the lifespan handler.
        """
        if self.is_loaded:
            return

        if self._store_file.exists() and self._store_file.stat().st_size > 0:
            try:
                with open(self._store_file, "r", encoding="utf-8") as fh:
                    loaded: dict[str, Any] = json.load(fh)
                if isinstance(loaded, dict) and "invoices" in loaded:
                    self._data = loaded
                    logger.info(
                        "Store loaded: %d invoices from %s",
                        len(self._data.get("invoices", [])),
                        self._store_file,
                    )
                else:
                    logger.warning(
                        "store.json has unexpected format — starting with empty store."
                    )
                    self._data = {"uploaded_at": None, "source_filename": None, "invoices": []}
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Failed to load store.json (%s) — starting empty.", exc)
                self._data = {"uploaded_at": None, "source_filename": None, "invoices": []}
        else:
            logger.info("store.json not found or empty — starting with empty store.")
            self._data = {"uploaded_at": None, "source_filename": None, "invoices": []}

        self.is_loaded = True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_invoices(self) -> list[dict[str, Any]]:
        """Return the raw list of invoice dicts from the in-memory store.

        Lazily triggers load_store() if called before startup (defensive).
        """
        if not self.is_loaded:
            logger.warning("get_invoices() called before load_store() — loading now.")
            self.load_store()
        return list(self._data.get("invoices", []))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_invoices(
        self,
        invoices_data: list[dict[str, Any]],
        *,
        uploaded_at: str | None = None,
        source_filename: str | None = None,
    ) -> None:
        """Atomically replace the store contents.

        Writes to a temporary file then renames it to store.json.  The
        ``threading.Lock`` prevents concurrent writes within the same process.

        Args:
            invoices_data: List of raw invoice dicts (no computed fields).
            uploaded_at: ISO-8601 timestamp of the upload (IST).
            source_filename: Original filename of the uploaded sheet.
        """
        with self._write_lock:
            self._data["invoices"] = invoices_data
            if uploaded_at is not None:
                self._data["uploaded_at"] = uploaded_at
            if source_filename is not None:
                self._data["source_filename"] = source_filename

            tmp_path: Path = self._store_file.with_suffix(".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self._store_file)
                logger.info(
                    "Store saved: %d invoices to %s", len(invoices_data), self._store_file
                )
            except (OSError, ValueError) as exc:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise FileSaveError(f"Failed to save store: {exc}") from exc


# ---------------------------------------------------------------------------
# Module-level singleton — imported by routers
# ---------------------------------------------------------------------------
store_instance: Store = Store.get_instance()
