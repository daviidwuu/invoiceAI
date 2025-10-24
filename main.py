"""Entry point for InvoiceAI application."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from gui import launch_app

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


def main() -> None:
    _setup_logging()
    _ensure_scaffolding()
    settings_path = CONFIG_DIR / "user_settings.json"
    known_entities_path = CONFIG_DIR / "known_entities.json"
    logger.info("Starting InvoiceAI application")
    launch_app(settings_path, known_entities_path)


if __name__ == "__main__":
    main()
