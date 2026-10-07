"""Data sources. Each returns every tab as a raw value grid; parsing happens in services.sheets.

- MockJsonSource:     reads data/mock_sheet.json — works out of the box, no credentials.
- CsvSource:          reads exported tabs as .csv files (DATA_SOURCE=csv, CSV_PATH).
- GoogleSheetsSource: reads the live Google Sheet with a service account (credentials.json).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Protocol

from .core.config import Settings
from .services.sheets import RawTabs, select_tabs


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

    Setup: create a service account in Google Cloud, enable the Sheets API, download its key
    as backend/credentials.json, and share the spreadsheet with the service account's email
    (Viewer access is enough).
    """

    name = "google"

    def __init__(self, credentials_file: Path, sheet_id: str, tab_filter: str = ""):
        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is required when DATA_SOURCE=google")
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.tab_filter = tab_filter
        self._spreadsheet = None

    def _open(self):
        if self._spreadsheet is None:
            import gspread  # imported lazily so mock mode doesn't need Google libs at all

            client = gspread.service_account(
                filename=str(self.credentials_file),
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
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
    if settings.data_source == "google":
        return GoogleSheetsSource(
            settings.google_credentials_file, settings.google_sheet_id, settings.tab_filter
        )
    if settings.data_source == "csv":
        return CsvSource(settings.csv_path)
    return MockJsonSource(settings.mock_file)
