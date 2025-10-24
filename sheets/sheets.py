"""Google Sheets integration utilities."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loguru import logger

try:  # pragma: no cover - optional dependency
    import gspread  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    gspread = None

try:  # pragma: no cover - optional dependency
    from google.oauth2.service_account import Credentials  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    Credentials = None


SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class SheetSync:
    """Handles interactions with Google Sheets including retries and locking."""

    _lock = threading.Lock()

    def __init__(
        self,
        credentials_path: Path = Path("config/credentials.json"),
        spreadsheet_name: str = "InvoiceAI Records",
    ) -> None:
        self.credentials_path = credentials_path
        self.spreadsheet_name = spreadsheet_name
        self._client = None
        self._sheet_cache: Dict[str, object] = {}
        self._ensure_dependencies()

    def _ensure_dependencies(self) -> None:
        if gspread is None or Credentials is None:
            logger.warning(
                "Sheets dependencies missing",
                gspread_installed=gspread is not None,
                credentials_available=Credentials is not None,
            )
        else:
            logger.debug("Sheets dependencies available")

    def _authenticate(self) -> Optional[object]:
        if gspread is None or Credentials is None:
            return None
        if self._client:
            return self._client
        if not self.credentials_path.exists():
            logger.error(
                "Credentials file missing",
                expected=str(self.credentials_path),
            )
            return None
        try:
            creds = Credentials.from_service_account_file(
                str(self.credentials_path), scopes=SCOPE
            )
            self._client = gspread.authorize(creds)
            logger.info("Authenticated with Google Sheets", spreadsheet=self.spreadsheet_name)
        except Exception as exc:  # pragma: no cover - external call
            logger.exception("Failed to authenticate with Google Sheets", error=str(exc))
            self._client = None
        return self._client

    def ensure_sheet(self) -> Optional[object]:
        client = self._authenticate()
        if client is None:
            return None
        if self.spreadsheet_name in self._sheet_cache:
            return self._sheet_cache[self.spreadsheet_name]
        try:
            sheet = client.open(self.spreadsheet_name)
        except Exception:  # pragma: no cover - external call
            logger.info("Creating spreadsheet", name=self.spreadsheet_name)
            sheet = client.create(self.spreadsheet_name)
        self._sheet_cache[self.spreadsheet_name] = sheet
        return sheet

    @contextmanager
    def _locked(self):
        logger.debug("Acquiring sheet lock")
        with SheetSync._lock:
            yield
        logger.debug("Released sheet lock")

    def upsert_records(self, records: Iterable[Dict[str, object]], worksheet_name: str = "Records") -> bool:
        sheet = self.ensure_sheet()
        if sheet is None:
            logger.error("Sheet not available; aborting upsert")
            return False

        with self._locked():
            try:
                worksheet = self._get_or_create_worksheet(sheet, worksheet_name)
                existing_records = worksheet.get_all_records()  # pragma: no cover - external
                existing_uids = {record.get("uid") for record in existing_records}
                new_rows = []
                for record in records:
                    uid = record.get("uid")
                    if not uid:
                        logger.warning("Skipping record without UID", record=record)
                        continue
                    if uid in existing_uids:
                        logger.debug("Updating existing row", uid=uid)
                        self._update_row(worksheet, uid, record)
                    else:
                        logger.debug("Adding new row", uid=uid)
                        new_rows.append(record)
                        existing_uids.add(uid)
                if new_rows:
                    headers = self._ensure_headers(worksheet, new_rows)
                    rows = [[record.get(header, "") for header in headers] for record in new_rows]
                    self._with_retry(worksheet.append_rows, rows)
                return True
            except Exception as exc:  # pragma: no cover - external
                logger.exception("Failed to upsert records", error=str(exc))
                return False

    def _with_retry(self, func, *args, **kwargs):  # pragma: no cover - external
        delay = 1.0
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                if attempt == 4:
                    logger.exception("Exceeded retries for Sheets operation", error=str(exc))
                    raise
                logger.warning(
                    "Sheets API limit encountered; retrying",
                    attempt=attempt + 1,
                    delay=delay,
                )
                time.sleep(delay)
                delay *= 2

    def _update_row(self, worksheet, uid: str, record: Dict[str, object]):  # pragma: no cover - external
        records = worksheet.get_all_records()
        headers = worksheet.row_values(1)
        for idx, row in enumerate(records, start=2):
            if str(row.get("uid")) == str(uid):
                values = [record.get(header, row.get(header, "")) for header in headers]
                self._with_retry(worksheet.update, f"A{idx}:{self._column_letter(len(headers))}{idx}", [values])
                logger.info("Updated row", uid=uid)
                return
        logger.warning("UID not found during update", uid=uid)

    def _ensure_headers(self, worksheet, new_rows: List[Dict[str, object]]):  # pragma: no cover
        headers = worksheet.row_values(1)
        if not headers:
            headers = sorted({key for row in new_rows for key in row.keys()})
            worksheet.append_row(headers)
            logger.debug("Initialized worksheet headers", headers=headers)
        return headers

    def _get_or_create_worksheet(self, sheet, worksheet_name: str):  # pragma: no cover - external
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except Exception:
            logger.info("Creating worksheet", name=worksheet_name)
            worksheet = sheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
        return worksheet

    def _column_letter(self, idx: int) -> str:
        letters = ""
        while idx > 0:
            idx, remainder = divmod(idx - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters or "A"


__all__ = ["SheetSync"]
