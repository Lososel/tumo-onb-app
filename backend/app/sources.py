"""Data sources. Each returns raw tab rows; parsing/whitelisting happens in sheet.parse_tabs.

- MockJsonSource:     reads data/mock_sheet.json — works out of the box, no credentials.
- GoogleSheetsSource: reads the live Google Sheet with a service account (credentials.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .config import Settings
from .sheet import TABS, RawTabs, rows_to_records


class DataSource(Protocol):
    name: str

    def fetch(self) -> RawTabs: ...


class MockJsonSource:
    name = "mock"

    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> RawTabs:
        with self.path.open(encoding="utf-8") as f:
            data = json.load(f)
        return {tab: data.get(tab, []) for tab in TABS}


class GoogleSheetsSource:
    """Reads all tabs in a single batched API call to stay well under Google's quotas.

    Setup: create a service account in Google Cloud, enable the Sheets API, download its key
    as backend/credentials.json, and share the spreadsheet with the service account's email
    (Viewer access is enough).
    """

    name = "google"

    def __init__(self, credentials_file: Path, sheet_id: str):
        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is required when DATA_SOURCE=google")
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
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
            result = self._open().values_batch_get(list(TABS))
        except Exception:
            self._spreadsheet = None  # force a fresh connection next time
            raise
        out: RawTabs = {}
        for tab, value_range in zip(TABS, result.get("valueRanges", [])):
            out[tab] = rows_to_records(value_range.get("values", []))
        return out


def build_source(settings: Settings) -> DataSource:
    if settings.data_source == "google":
        return GoogleSheetsSource(settings.google_credentials_file, settings.google_sheet_id)
    return MockJsonSource(settings.mock_file)
