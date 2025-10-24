"""PDF extraction utilities for InvoiceAI."""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pdfplumber  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None

try:
    from pypdf import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    from pdf2image import convert_from_path  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    convert_from_path = None

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pytesseract = None

from loguru import logger


@dataclass
class FieldCandidate:
    """Represents a potential field detected within the PDF."""

    field_name: str
    value: str
    confidence: float
    page_number: int
    snippet: Optional[str] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    source: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Structured output describing extraction results for a document."""

    source_path: Path
    pages: List[Dict[str, object]]
    field_candidates: List[FieldCandidate]
    ocr_used: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "source_path": str(self.source_path),
                "ocr_used": self.ocr_used,
                "pages": self.pages,
                "field_candidates": [
                    {
                        "field_name": candidate.field_name,
                        "value": candidate.value,
                        "confidence": candidate.confidence,
                        "page_number": candidate.page_number,
                        "snippet": candidate.snippet,
                        "bbox": candidate.bbox,
                        "source": candidate.source,
                        "metadata": candidate.metadata,
                    }
                    for candidate in self.field_candidates
                ],
            },
            indent=2,
        )


class Extractor:
    """Handles PDF text extraction and OCR fallbacks."""

    def __init__(
        self,
        ocr_threshold: float = 0.35,
        max_pages_for_snippet: int = 2,
        tesseract_lang: str = "eng",
    ) -> None:
        self.ocr_threshold = ocr_threshold
        self.max_pages_for_snippet = max_pages_for_snippet
        self.tesseract_lang = tesseract_lang
        logger.debug(
            "Extractor initialized",
            ocr_threshold=ocr_threshold,
            max_pages_for_snippet=max_pages_for_snippet,
            tesseract_lang=tesseract_lang,
        )

    def process_pdf(self, pdf_path: Path, force_ocr: bool = False) -> ExtractionResult:
        """Extracts information from the PDF using text extraction or OCR."""
        if not pdf_path.exists():
            logger.error("PDF path does not exist", path=str(pdf_path))
            raise FileNotFoundError(pdf_path)

        logger.info("Starting PDF extraction", path=str(pdf_path))
        pages: List[Dict[str, object]] = []
        ocr_used = force_ocr
        if not force_ocr:
            pages = self._extract_with_pdfplumber(pdf_path)
            logger.debug("Text extraction result", page_count=len(pages))
            avg_conf = statistics.mean(
                page.get("confidence", self.ocr_threshold) for page in pages
            ) if pages else 0
            if avg_conf < self.ocr_threshold:
                logger.warning(
                    "Average confidence below threshold; switching to OCR",
                    avg_conf=avg_conf,
                    threshold=self.ocr_threshold,
                )
                ocr_used = True

        if not pages and not ocr_used:
            logger.info("Falling back to PyPDF text extraction", path=str(pdf_path))
            pages = self._extract_with_pypdf(pdf_path)

        if force_ocr or ocr_used or not pages:
            logger.info("Performing OCR on PDF", path=str(pdf_path))
            pages = self._extract_with_ocr(pdf_path)
            ocr_used = True

        candidates = self._generate_field_candidates(pdf_path, pages)
        result = ExtractionResult(
            source_path=pdf_path,
            pages=pages,
            field_candidates=candidates,
            ocr_used=ocr_used,
        )
        logger.info(
            "Finished PDF extraction",
            path=str(pdf_path),
            candidates=len(candidates),
            ocr_used=ocr_used,
        )
        return result

    def _extract_with_pdfplumber(self, pdf_path: Path) -> List[Dict[str, object]]:
        if pdfplumber is None:
            logger.error("pdfplumber is not installed; cannot perform direct extraction")
            return []
        pages: List[Dict[str, object]] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for index, page in enumerate(pdf.pages):
                    words = page.extract_words(use_text_flow=True)
                    text = page.extract_text() or ""
                    confidence = self._estimate_page_confidence_from_words(words)
                    pages.append(
                        {
                            "index": index,
                            "text": text,
                            "words": words,
                            "confidence": confidence,
                        }
                    )
        except Exception as exc:  # pragma: no cover - integration path
            logger.exception("Failed to extract with pdfplumber", error=str(exc))
            return []

    def _extract_with_pypdf(self, pdf_path: Path) -> List[Dict[str, object]]:
        if PdfReader is None:
            logger.warning("PyPDF is not installed; skipping fallback text extraction")
            return []
        try:
            reader = PdfReader(str(pdf_path))
        except Exception as exc:  # pragma: no cover - integration path
            logger.exception("Unable to open PDF with PyPDF", error=str(exc))
            return []
        pages: List[Dict[str, object]] = []
        for index, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # pragma: no cover - integration path
                logger.exception("PyPDF failed to extract text", page=index, error=str(exc))
                text = ""
            pages.append({"index": index, "text": text, "words": [], "confidence": 0.5})
        return pages

    def _extract_with_ocr(self, pdf_path: Path) -> List[Dict[str, object]]:
        if convert_from_path is None or pytesseract is None:
            logger.error(
                "OCR dependencies missing",
                convert_from_path_available=convert_from_path is not None,
                pytesseract_available=pytesseract is not None,
            )
            return []

        pages: List[Dict[str, object]] = []
        try:
            images = convert_from_path(str(pdf_path))
            for index, image in enumerate(images):
                text = pytesseract.image_to_string(image, lang=self.tesseract_lang)
                data = pytesseract.image_to_data(image, lang=self.tesseract_lang, output_type=pytesseract.Output.DICT)
                words = []
                for i in range(len(data["text"])):
                    if not data["text"][i].strip():
                        continue
                    x, y, w, h = (
                        data["left"][i],
                        data["top"][i],
                        data["width"][i],
                        data["height"][i],
                    )
                    words.append(
                        {
                            "text": data["text"][i],
                            "x0": x,
                            "top": y,
                            "x1": x + w,
                            "bottom": y + h,
                        }
                    )
                pages.append(
                    {
                        "index": index,
                        "text": text,
                        "words": words,
                        "confidence": self._estimate_page_confidence_from_words(words),
                    }
                )
        except Exception as exc:  # pragma: no cover - integration path
            logger.exception("OCR extraction failed", error=str(exc))
            return []
        return pages

    @staticmethod
    def _estimate_page_confidence_from_words(words: Sequence[Dict[str, object]]) -> float:
        if not words:
            return 0.0
        lengths = [len(word.get("text", "")) for word in words if word.get("text")]
        unique = len({word.get("text") for word in words if word.get("text")})
        if not lengths:
            return 0.0
        length_score = min(statistics.mean(lengths) / 10.0, 1.0)
        diversity_score = min(unique / (len(words) + 1e-5), 1.0)
        return round((length_score + diversity_score) / 2.0, 2)

    def _generate_field_candidates(
        self, pdf_path: Path, pages: Sequence[Dict[str, object]]
    ) -> List[FieldCandidate]:
        logger.debug("Generating field candidates", path=str(pdf_path))
        text_stream = "\n".join(page.get("text", "") for page in pages)
        candidates: List[FieldCandidate] = []
        if not text_stream:
            logger.warning("No text available for candidate generation")
            return candidates

        patterns = {
            "invoice_id": re.compile(r"invoice\s*(?:number|no\.?|#)\s*[:#-]?\s*(\w+)", re.IGNORECASE),
            "invoice_date": re.compile(
                r"(?:invoice\s*)?(?:date)\s*[:#-]?\s*([0-9]{1,2}[\-/][0-9]{1,2}[\-/][0-9]{2,4})",
                re.IGNORECASE,
            ),
            "total": re.compile(
                r"total\s*(?:due|amount)?\s*[:#-]?\s*([$€£]?\s?[0-9,.]+)",
                re.IGNORECASE,
            ),
        }

        for field, pattern in patterns.items():
            for match in pattern.finditer(text_stream):
                value = match.group(1).strip()
                page_index = self._locate_page_for_match(match.start(), pages)
                snippet = self._extract_snippet(match.start(), match.end(), text_stream)
                bbox = self._find_bbox_for_value(value, pages[page_index]["words"]) if pages else None
                confidence = self._confidence_from_match(value)
                candidates.append(
                    FieldCandidate(
                        field_name=field,
                        value=value,
                        confidence=confidence,
                        page_number=page_index,
                        snippet=snippet,
                        bbox=bbox,
                        source="regex",
                        metadata={"pattern": pattern.pattern},
                    )
                )
                logger.debug(
                    "Field candidate generated",
                    field=field,
                    value=value,
                    page=page_index,
                    confidence=confidence,
                )

        vendor_candidate = self._guess_vendor(pages)
        if vendor_candidate:
            candidates.append(vendor_candidate)

        return candidates

    def _locate_page_for_match(
        self, char_index: int, pages: Sequence[Dict[str, object]]
    ) -> int:
        cumulative = 0
        for page in pages:
            text = page.get("text", "")
            length = len(text) + 1
            if char_index < cumulative + length:
                return page.get("index", 0)
            cumulative += length
        return 0

    def _extract_snippet(self, start: int, end: int, text_stream: str) -> str:
        window = 60
        snippet = text_stream[max(0, start - window) : min(len(text_stream), end + window)]
        return snippet.replace("\n", " ")

    def _find_bbox_for_value(
        self, value: str, words: Iterable[Dict[str, object]]
    ) -> Optional[Tuple[float, float, float, float]]:
        tokens = value.split()
        candidate_boxes = []
        for word in words:
            if word.get("text") and any(
                token.lower() in word.get("text", "").lower() for token in tokens
            ):
                candidate_boxes.append(
                    (
                        float(word.get("x0", 0)),
                        float(word.get("top", 0)),
                        float(word.get("x1", 0)),
                        float(word.get("bottom", 0)),
                    )
                )
        if not candidate_boxes:
            return None
        x0 = min(box[0] for box in candidate_boxes)
        y0 = min(box[1] for box in candidate_boxes)
        x1 = max(box[2] for box in candidate_boxes)
        y1 = max(box[3] for box in candidate_boxes)
        return (x0, y0, x1, y1)

    def _confidence_from_match(self, value: str) -> float:
        if not value:
            return 0.0
        numeric_ratio = sum(c.isdigit() for c in value) / len(value)
        confidence = 0.5 + (numeric_ratio * 0.5)
        return round(min(confidence, 0.99), 2)

    def _guess_vendor(self, pages: Sequence[Dict[str, object]]) -> Optional[FieldCandidate]:
        if not pages:
            return None
        first_page = pages[0]
        text = first_page.get("text", "").splitlines()
        header_lines = [line.strip() for line in text[:10] if line.strip()]
        if not header_lines:
            return None
        candidate = header_lines[0]
        confidence = 0.6 if len(candidate.split()) >= 2 else 0.4
        logger.debug("Vendor candidate", candidate=candidate, confidence=confidence)
        return FieldCandidate(
            field_name="vendor",
            value=candidate,
            confidence=confidence,
            page_number=first_page.get("index", 0),
            snippet=candidate,
            source="header",
        )


__all__ = ["FieldCandidate", "ExtractionResult", "Extractor"]
