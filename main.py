"""Entry point for InvoiceAI application."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from loguru import logger

from gui import launch_app
from invoice_processor import InvoiceProcessor

CONFIG_DIR = Path("config")
LOG_DIR = Path("logs")
DEFAULT_SETTINGS = {
    "auto_sync": True,
    "confidence_mode": "balanced",
}


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "app.log"
    logger.add(log_file, rotation="1 week", retention="1 month")
    logger.info("Logging configured", file=str(log_file))


def _ensure_scaffolding() -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    credentials_template = CONFIG_DIR / "credentials_template.json"
    if not credentials_template.exists():
        credentials_template.write_text(
            json.dumps(
                {
                    "type": "service_account",
                    "project_id": "your-project-id",
                    "private_key_id": "REPLACE_ME",
                    "private_key": "-----BEGIN PRIVATE KEY-----\\nREPLACE\\n-----END PRIVATE KEY-----\\n",
                    "client_email": "service-account@your-project-id.iam.gserviceaccount.com",
                    "client_id": "",
                    "token_uri": "https://oauth2.googleapis.com/token",
                },
                indent=2,
            )
        )
    user_settings = CONFIG_DIR / "user_settings.json"
    if not user_settings.exists():
        user_settings.write_text(json.dumps(DEFAULT_SETTINGS, indent=2))
    known_entities = CONFIG_DIR / "known_entities.json"
    if not known_entities.exists():
        known_entities.write_text(
            json.dumps(
                {
                    "vendors": {
                        "acme-001": {
                            "name": "Acme Corporation",
                            "confidence": 0.95,
                            "address": "123 Industry Way, Springfield",
                            "code": "ACM",
                        }
                    }
                },
                indent=2,
            )
        )
    logs_history = LOG_DIR / "training_history.csv"
    if not logs_history.exists():
        logs_history.write_text("timestamp,feedback_records,model_version,status\n")
    feedback_file = Path("training_data/feedback.jsonl")
    feedback_file.parent.mkdir(parents=True, exist_ok=True)
    if not feedback_file.exists():
        feedback_file.touch()


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Process invoice PDFs into tabular rows or launch the GUI",
    )
    parser.add_argument("pdf", nargs="?", help="Path to the invoice PDF to process")
    parser.add_argument(
        "--vendor-code",
        help="Override vendor/project code when generating the TSV output",
    )
    parser.add_argument(
        "--tsv-out",
        help="Optional path to save the generated TSV line (prints to stdout when omitted)",
    )
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="Also emit the structured parsing result as JSON",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the desktop GUI instead of running the CLI workflow",
    )

    args = parser.parse_args(argv)

    _setup_logging()
    _ensure_scaffolding()
    settings_path = CONFIG_DIR / "user_settings.json"
    known_entities_path = CONFIG_DIR / "known_entities.json"
    logger.info("Starting InvoiceAI", mode="gui" if args.gui else "cli")

    if args.gui:
        launch_app(settings_path, known_entities_path)
        return

    if not args.pdf:
        parser.print_help()
        sys.exit(1)

    processor = InvoiceProcessor()
    record, _, parse_result = processor.process(Path(args.pdf), args.vendor_code)
    line = record.to_tsv()

    if args.tsv_out:
        output_path = Path(args.tsv_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(line + "\n")
        logger.info("Wrote TSV output", path=str(output_path))
    else:
        print(line)

    if args.emit_json:
        print(parse_result.to_json())



if __name__ == "__main__":
    main()
