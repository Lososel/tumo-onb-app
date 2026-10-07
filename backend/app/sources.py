"""Data sources. Each returns every tab as a raw value grid; parsing happens in services.sheets.

- MockJsonSource:     reads data/mock_sheet.json — works out of the box, no credentials.
- CsvSource:          reads exported tabs as .csv files (DATA_SOURCE=csv, CSV_PATH).
- GoogleSheetsSource: reads the live Google Sheet with a service account (credentials.json).
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Protocol

from .core.config import Settings
from .services.sheets import (
    RawTabs,
    SheetsConfigError,
    load_credentials_file,
    parse_credentials_json,
    select_tabs,
)

log = logging.getLogger(__name__)


class DataSource(Protocol):
    name: str

    def fetch(self) -> RawTabs: ...


class MockJsonSource:
    """Mock file format: {"Tab title": [[header...], [row...], ...], ...} — same as the live sheet."""

    name = "mock"

    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> RawTabs:
        with self.path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("mock sheet must be an object of {tab title: [[row], ...]}")
        return {str(tab): list(grid) for tab, grid in data.items()}


class CsvSource:
    """Reads exported sheet tabs as CSV files: one file = one tab (titled by the file name).

    `path` may be a single .csv file or a folder of them. Real exports contain personal data;
    keep them out of git (backend/data/csv/ is ignored).
    """

    name = "csv"

    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> RawTabs:
        files = sorted(self.path.glob("*.csv")) if self.path.is_dir() else [self.path]
        if not files:
            raise FileNotFoundError(f"no .csv files in {self.path}")
        out: RawTabs = {}
        for file in files:
            with file.open(encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel/Sheets BOM
                out[file.stem] = list(csv.reader(f))
        return out


class GoogleSheetsSource:
    """Reads every tab: one metadata call lists the tabs, one batched call reads them all.

    Setup: create a service account in Google Cloud, enable the Sheets API, and share the
    spreadsheet with the service account's email (Viewer access is enough). Provide the key
    either as GOOGLE_CREDENTIALS_JSON (raw JSON) or as a file (GOOGLE_CREDENTIALS_FILE).

    Construction never fails: a missing sheet id or bad credentials surface as a
    SheetsConfigError on fetch(), which the store treats like any other sync failure.
    """

    name = "google"
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    def __init__(
        self, credentials_file: Path, sheet_id: str, tab_filter: str = "", credentials_json: str = ""
    ):
        self.credentials_file = credentials_file
        self.credentials_json = credentials_json
        self.sheet_id = sheet_id
        self.tab_filter = tab_filter
        self._spreadsheet = None

    def _credentials(self) -> dict:
        if self.credentials_json.strip():
            return parse_credentials_json(self.credentials_json)
        return load_credentials_file(self.credentials_file)

    def _open(self):
        if self._spreadsheet is None:
            if not self.sheet_id:
                raise SheetsConfigError("GOOGLE_SHEET_ID is not set")
            info = self._credentials()
            import gspread  # imported lazily so mock mode doesn't need Google libs at all

            try:
                client = gspread.service_account_from_dict(info, scopes=self.SCOPES)
            except (ValueError, KeyError) as exc:  # e.g. a malformed private key
                raise SheetsConfigError(f"service-account key rejected ({type(exc).__name__})") from None
            client.set_timeout(15)
            self._spreadsheet = client.open_by_key(self.sheet_id)
        return self._spreadsheet

    def fetch(self) -> RawTabs:
        try:
            spreadsheet = self._open()
            # Picks up newly added tabs; with TAB_FILTER only the matching tabs are downloaded,
            # so other batches' data never reaches this server.
            titles = select_tabs([ws.title for ws in spreadsheet.worksheets()], self.tab_filter)
            # Quote titles so names with spaces or punctuation are valid A1 ranges.
            ranges = ["'" + t.replace("'", "''") + "'" for t in titles]
            result = spreadsheet.values_batch_get(ranges) if ranges else {}
        except Exception:
            self._spreadsheet = None  # force a fresh connection next time
            raise
        return {
            title: value_range.get("values", [])
            for title, value_range in zip(titles, result.get("valueRanges", []))
        }


def build_source(settings: Settings) -> DataSource:
    """Never raises: configuration problems show up as sync errors, not as a crashed app."""
    if settings.data_source == "google":
        return GoogleSheetsSource(
            settings.google_credentials_file,
            settings.google_sheet_id,
            settings.tab_filter,
            credentials_json=settings.google_credentials_json,
        )
    if settings.data_source == "csv":
        return CsvSource(settings.csv_path)
    if settings.data_source not in ("", "mock"):
        log.warning("Unknown DATA_SOURCE=%r; using the mock dataset", settings.data_source)
    return MockJsonSource(settings.mock_file)


def build_fallback_source(settings: Settings) -> DataSource | None:
    """Mock dataset used only when live data and the cache are both unavailable (opt-in)."""
    if settings.fallback_to_mock and settings.data_source != "mock":
        return MockJsonSource(settings.mock_file)
    return None
