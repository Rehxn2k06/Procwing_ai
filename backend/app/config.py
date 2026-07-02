"""backend/app/config.py — Application settings and constants."""

from __future__ import annotations

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load .env from the backend/ directory regardless of the working directory.
_BACKEND_DIR: Path = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(_BACKEND_DIR / ".env")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timezone constant — single source of truth for IST across the application.
# ---------------------------------------------------------------------------
IST: ZoneInfo = ZoneInfo("Asia/Kolkata")


class Settings:
    """Centralised application settings.

    Paths are resolved relative to the backend/ directory so the app starts
    correctly regardless of the process working directory.
    """

    # Path to the JSON data store.
    DATA_DIR: Path = _BACKEND_DIR / "data"
    STORE_FILE: Path = DATA_DIR / "store.json"

    # CORS — local Vite dev server.
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    def __init__(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug("Settings initialised. Store file: %s", self.STORE_FILE)


settings: Settings = Settings()
