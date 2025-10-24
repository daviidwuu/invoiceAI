"""High-level orchestration utilities for turning PDFs into tabular rows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

from extract import ExtractionResult, Extractor
from parse import InvoiceParser, ParseResult


@dataclass
class InvoiceRecord:
    """Represents the tabular output expected by downstream systems."""

    invoice_date: str
    invoice_number: str
    address: str
    description: str
    amount: str
    vendor_code: str

    def to_tsv(self) -> str:
        """Return the record encoded as a tab-separated line."""

        return "\t".join(
            [
                self.invoice_date,
                self.invoice_number,
                self.address,
                self.description,
                self.amount,
                self.vendor_code,
            ]
        )


class InvoiceProcessor:
    """Convenience wrapper that wires together extraction and parsing."""

    def __init__(
        self,
        extractor: Optional[Extractor] = None,
        parser: Optional[InvoiceParser] = None,
    ) -> None:
        self.extractor = extractor or Extractor()
        self.parser = parser or InvoiceParser()

    def process(
        self, pdf_path: Path, override_vendor_code: Optional[str] = None
    ) -> Tuple[InvoiceRecord, ExtractionResult, ParseResult]:
        """Process a PDF and return the final record along with raw artefacts."""

        logger.info("Processing invoice", path=str(pdf_path))
        extraction = self.extractor.process_pdf(pdf_path)
        parse_result = self.parser.parse(extraction)
        record = self._build_record(parse_result, override_vendor_code)
        logger.info("Derived invoice record", record=record)
        return record, extraction, parse_result

    def _build_record(
        self, parse_result: ParseResult, override_vendor_code: Optional[str]
    ) -> InvoiceRecord:
        def _field_value(field, fallback: str = "") -> str:
            return field.value.strip() if field and field.value else fallback

        vendor_code = override_vendor_code or _field_value(parse_result.project_code)
        if not vendor_code and parse_result.vendor:
            vendor_code = str(
                parse_result.vendor.metadata.get("code", "")
            ).strip()

        return InvoiceRecord(
            invoice_date=_field_value(parse_result.invoice_date),
            invoice_number=_field_value(parse_result.invoice_id),
            address=_field_value(parse_result.address),
            description=_field_value(parse_result.description),
            amount=_field_value(parse_result.total),
            vendor_code=vendor_code or "UNKNOWN",
        )


__all__ = ["InvoiceProcessor", "InvoiceRecord"]

