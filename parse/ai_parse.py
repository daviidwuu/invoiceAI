"""Local AI parsing utilities for InvoiceAI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

try:  # pragma: no cover - optional dependency
    import spacy  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    spacy = None


@dataclass
class ParsedField:
    name: str
    value: str
    confidence: float
    source: str
    reasoning: str


@dataclass
class ParseResult:
    vendor: Optional[ParsedField]
    invoice_id: Optional[ParsedField]
    invoice_date: Optional[ParsedField]
    total: Optional[ParsedField]
    line_items: List[Dict[str, str]] = field(default_factory=list)
    additional_entities: List[ParsedField] = field(default_factory=list)
    reasoning_steps: List[Dict[str, str]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "vendor": self.vendor.__dict__ if self.vendor else None,
                "invoice_id": self.invoice_id.__dict__ if self.invoice_id else None,
                "invoice_date": self.invoice_date.__dict__ if self.invoice_date else None,
                "total": self.total.__dict__ if self.total else None,
                "line_items": self.line_items,
                "additional_entities": [field.__dict__ for field in self.additional_entities],
                "reasoning_steps": self.reasoning_steps,
            },
            indent=2,
        )


class InvoiceParser:
    """Parses extraction results using local NLP strategies."""

    def __init__(
        self,
        model_name: str = "en_core_web_sm",
        known_entities_path: Path = Path("config/known_entities.json"),
    ) -> None:
        self.model_name = model_name
        self.known_entities_path = known_entities_path
        self._nlp = None
        self.known_entities = self._load_known_entities()
        logger.debug("InvoiceParser initialized", model=model_name)

    def _load_known_entities(self) -> Dict[str, Dict[str, str]]:
        if not self.known_entities_path.exists():
            logger.warning(
                "Known entities file missing", path=str(self.known_entities_path)
            )
            return {}
        try:
            data = json.loads(self.known_entities_path.read_text())
            logger.debug(
                "Loaded known entities",
                count=sum(len(v) for v in data.values()) if isinstance(data, dict) else 0,
            )
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse known entities", path=str(self.known_entities_path), error=str(exc)
            )
            return {}

    def _load_model(self) -> None:
        if self._nlp is not None:
            return
        if spacy is None:
            logger.warning("spaCy not installed; using rule-based parsing only")
            return
        try:  # pragma: no cover - depends on runtime
            self._nlp = spacy.load(self.model_name)
            logger.info("Loaded spaCy model", model=self.model_name)
        except Exception as exc:  # pragma: no cover - optional path
            logger.exception(
                "Failed to load spaCy model", model=self.model_name, error=str(exc)
            )
            self._nlp = None

    def parse(self, extraction_result) -> ParseResult:
        """Parse an :class:`extract.ExtractionResult` into structured data."""
        self._load_model()
        text = "\n".join(page.get("text", "") for page in extraction_result.pages)
        reasoning_steps: List[Dict[str, str]] = []
        parsed_fields = {
            "vendor": self._match_known_entity(text, reasoning_steps),
            "invoice_id": self._regex_extract(
                text, r"invoice\s*(?:number|no\.?|#)\s*[:#-]?\s*(\w+)", "Invoice number"
            ),
            "invoice_date": self._regex_extract(
                text,
                r"(?:invoice\s*)?(?:date)\s*[:#-]?\s*([0-9]{1,2}[\-/][0-9]{1,2}[\-/][0-9]{2,4})",
                "Invoice date",
            ),
            "total": self._regex_extract(
                text,
                r"total\s*(?:due|amount)?\s*[:#-]?\s*([$€£]?\s?[0-9,.]+)",
                "Total amount",
            ),
        }

        if self._nlp is not None:
            doc = self._nlp(text)
            additional_entities = self._extract_from_model(doc, reasoning_steps)
        else:
            additional_entities = []

        line_items = self._extract_line_items(text, reasoning_steps)

        result = ParseResult(
            vendor=parsed_fields["vendor"],
            invoice_id=parsed_fields["invoice_id"],
            invoice_date=parsed_fields["invoice_date"],
            total=parsed_fields["total"],
            line_items=line_items,
            additional_entities=additional_entities,
            reasoning_steps=reasoning_steps,
        )
        logger.info("Completed parsing", vendor=result.vendor.value if result.vendor else None)
        return result

    def _match_known_entity(
        self, text: str, reasoning_steps: List[Dict[str, str]]
    ) -> Optional[ParsedField]:
        vendors = self.known_entities.get("vendors", {})
        for uid, vendor in vendors.items():
            name = vendor.get("name", "")
            if name and name.lower() in text.lower():
                reasoning_steps.append(
                    {
                        "field": "vendor",
                        "method": "known-entity",
                        "detail": f"Matched vendor '{name}' by UID {uid}",
                    }
                )
                confidence = float(vendor.get("confidence", 0.9))
                return ParsedField(
                    name="vendor",
                    value=name,
                    confidence=confidence,
                    source="known_entity",
                    reasoning=f"Matched known vendor {name}",
                )
        return None

    def _regex_extract(
        self, text: str, pattern: str, label: str
    ) -> Optional[ParsedField]:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            logger.debug("Regex did not match", pattern=pattern)
            return None
        value = match.group(1).strip()
        confidence = min(0.95, 0.6 + len(value) / 30)
        reasoning = f"Detected {label.lower()} via regex"
        logger.debug("Regex match", label=label, value=value, confidence=confidence)
        return ParsedField(
            name=label.lower().replace(" ", "_"),
            value=value,
            confidence=round(confidence, 2),
            source="regex",
            reasoning=reasoning,
        )

    def _extract_from_model(
        self, doc, reasoning_steps: List[Dict[str, str]]
    ) -> List[ParsedField]:  # pragma: no cover - depends on spaCy
        entities: List[ParsedField] = []
        for ent in doc.ents:
            label = ent.label_.lower()
            if label in {"vendor", "org", "company"}:
                reasoning_steps.append(
                    {
                        "field": "vendor",
                        "method": "spacy-ner",
                        "detail": f"Detected organization entity '{ent.text}'",
                    }
                )
            entities.append(
                ParsedField(
                    name=label,
                    value=ent.text,
                    confidence=getattr(ent, "kb_id_", None) or 0.5,
                    source="spacy",
                    reasoning=f"Detected entity {ent.text} ({ent.label_})",
                )
            )
        return entities

    def _extract_line_items(
        self, text: str, reasoning_steps: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        line_items: List[Dict[str, str]] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        item_pattern = re.compile(r"^(?P<desc>.+?)\s+(?P<qty>\d+)\s+(?P<price>[$€£]?\s?[0-9,.]+)$")
        for line in lines:
            match = item_pattern.match(line)
            if match:
                item = {
                    "description": match.group("desc"),
                    "quantity": match.group("qty"),
                    "price": match.group("price"),
                }
                line_items.append(item)
        if line_items:
            reasoning_steps.append(
                {
                    "field": "line_items",
                    "method": "regex-table",
                    "detail": f"Detected {len(line_items)} potential line items",
                }
            )
        return line_items


__all__ = ["InvoiceParser", "ParseResult", "ParsedField"]
