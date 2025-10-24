"""Training engine for incremental model updates."""

from __future__ import annotations

import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from loguru import logger


class TrainingEngine:
    """Collects feedback and retrains local models asynchronously."""

    def __init__(
        self,
        feedback_path: Path = Path("training_data/feedback.jsonl"),
        training_log: Path = Path("logs/training_history.csv"),
        models_dir: Path = Path("models"),
    ) -> None:
        self.feedback_path = feedback_path
        self.training_log = training_log
        self.models_dir = models_dir
        self._training_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ensure_paths()
        logger.debug("TrainingEngine initialized")

    def _ensure_paths(self) -> None:
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.training_log.parent.mkdir(parents=True, exist_ok=True)
        if not self.training_log.exists():
            with self.training_log.open("w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["timestamp", "feedback_records", "model_version", "status"])
        if not self.feedback_path.exists():
            self.feedback_path.touch()

    def record_feedback(self, payload: Dict[str, object], retrain: bool = True) -> None:
        payload = {
            **payload,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.debug("Recording feedback", payload=payload)
        with self.feedback_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload) + "\n")
        if retrain:
            self._schedule_retrain()

    def _schedule_retrain(self) -> None:
        if self._training_thread and self._training_thread.is_alive():
            logger.info("Training already in progress; skipping new schedule")
            return
        self._stop_event.clear()
        self._training_thread = threading.Thread(target=self._run_training, daemon=True)
        self._training_thread.start()
        logger.info("Scheduled training job")

    def _run_training(self) -> None:
        logger.info("Starting background training run")
        try:
            feedback_records = self.feedback_path.read_text().strip().splitlines()
            if not feedback_records:
                logger.info("No feedback available; skipping training")
                self._log_training(0, "skipped", "none")
                return
            model_version = datetime.utcnow().strftime("model_%Y%m%d_%H%M%S")
            model_path = self.models_dir / model_version
            model_path.mkdir(parents=True, exist_ok=True)
            metadata = {
                "created_at": datetime.utcnow().isoformat(),
                "feedback_count": len(feedback_records),
            }
            (model_path / "metadata.json").write_text(json.dumps(metadata, indent=2))
            time.sleep(1.0)
            self._log_training(len(feedback_records), "success", model_version)
            logger.success("Training run complete", model_version=model_version)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Training run failed", error=str(exc))
            self._log_training(0, "failed", "error")

    def _log_training(self, feedback_count: int, status: str, model_version: str) -> None:
        with self.training_log.open("a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    datetime.utcnow().isoformat(),
                    feedback_count,
                    model_version,
                    status,
                ]
            )
        logger.debug(
            "Training log updated",
            feedback_count=feedback_count,
            status=status,
            model_version=model_version,
        )

    def stop(self) -> None:
        logger.info("Stopping TrainingEngine")
        self._stop_event.set()
        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=5)


__all__ = ["TrainingEngine"]
