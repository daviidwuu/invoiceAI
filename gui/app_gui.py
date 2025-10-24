"""Application GUI built with PySide6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

try:  # pragma: no cover - optional dependency
    from PySide6.QtCore import Slot
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QComboBox,
        QCheckBox,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
    )
except ImportError:  # pragma: no cover - fallback path
    QApplication = None

from extract import Extractor
from parse import InvoiceParser
from sheets import SheetSync
from training import TrainingEngine


class InvoiceMainWindow(QMainWindow):  # pragma: no cover - GUI class
    def __init__(
        self,
        settings_path: Path,
        known_entities_path: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings_path = settings_path
        self.known_entities_path = known_entities_path
        self.extractor = Extractor()
        self.parser = InvoiceParser(known_entities_path=known_entities_path)
        self.sheet_sync = SheetSync()
        self.training_engine = TrainingEngine()
        self.current_result = None
        self._settings_data: Dict[str, object] = {}

        self.setWindowTitle("InvoiceAI Dashboard")
        self.resize(1200, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard_tab = QWidget()
        self.settings_tab = QWidget()
        self.training_tab = QWidget()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.training_tab, "Training")

        self._build_dashboard_tab()
        self._build_settings_tab()
        self._build_training_tab()

        self._load_settings()
        self._setup_menu()

    def _setup_menu(self) -> None:
        open_action = QAction("Open PDF", self)
        open_action.triggered.connect(self._choose_pdf)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction(open_action)

    def _build_dashboard_tab(self) -> None:
        layout = QVBoxLayout()
        controls = QHBoxLayout()

        self.pdf_path_display = QLineEdit()
        self.pdf_path_display.setPlaceholderText("Select a PDF to process")
        self.pdf_path_display.setReadOnly(True)

        select_button = QPushButton("Load PDF")
        select_button.clicked.connect(self._choose_pdf)

        self.process_button = QPushButton("Process")
        self.process_button.clicked.connect(self._process_pdf)

        self.confidence_mode = QComboBox()
        self.confidence_mode.addItems(["balanced", "conservative", "aggressive"])

        controls.addWidget(self.pdf_path_display)
        controls.addWidget(select_button)
        controls.addWidget(self.process_button)
        controls.addWidget(QLabel("Confidence"))
        controls.addWidget(self.confidence_mode)

        self.reasoning_view = QListWidget()
        self.extraction_output = QTextEdit()
        self.extraction_output.setReadOnly(True)

        self.entity_table = QTableWidget(0, 4)
        self.entity_table.setHorizontalHeaderLabels(["Field", "Value", "Confidence", "Source"])
        self.entity_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout.addLayout(controls)
        layout.addWidget(QLabel("Parsed Entities"))
        layout.addWidget(self.entity_table)
        layout.addWidget(QLabel("Reasoning"))
        layout.addWidget(self.reasoning_view)
        layout.addWidget(QLabel("Raw Extraction"))
        layout.addWidget(self.extraction_output)

        container = QWidget()
        container.setLayout(layout)
        self.dashboard_tab.setLayout(QVBoxLayout())
        self.dashboard_tab.layout().addWidget(container)

    def _build_settings_tab(self) -> None:
        layout = QGridLayout()
        self.auto_sync_checkbox = QCheckBox("Automatically sync to Google Sheets")
        layout.addWidget(self.auto_sync_checkbox, 0, 0, 1, 2)

        layout.addWidget(QLabel("Preferred Confidence Mode"), 1, 0)
        self.settings_confidence_mode = QComboBox()
        self.settings_confidence_mode.addItems(["balanced", "conservative", "aggressive"])
        layout.addWidget(self.settings_confidence_mode, 1, 1)

        save_button = QPushButton("Save Settings")
        save_button.clicked.connect(self._save_settings)
        layout.addWidget(save_button, 2, 0, 1, 2)

        self.settings_tab.setLayout(layout)

    def _build_training_tab(self) -> None:
        layout = QVBoxLayout()
        self.feedback_input = QTextEdit()
        self.feedback_input.setPlaceholderText("Provide feedback on the latest prediction...")
        submit_button = QPushButton("Submit Feedback")
        submit_button.clicked.connect(self._submit_feedback)

        layout.addWidget(QLabel("Feedback"))
        layout.addWidget(self.feedback_input)
        layout.addWidget(submit_button)

        self.training_tab.setLayout(layout)

    @Slot()
    def _choose_pdf(self) -> None:
        start_dir = self._settings_data.get("last_opened_dir") or str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select invoice PDF",
            start_dir,
            "PDF Files (*.pdf)",
        )
        if file_path:
            self.pdf_path_display.setText(file_path)
            self._settings_data["last_opened_dir"] = str(Path(file_path).parent)
            try:
                self._persist_settings()
            except Exception:
                pass

    @Slot()
    def _process_pdf(self) -> None:
        path = self.pdf_path_display.text()
        if not path:
            QMessageBox.warning(self, "No file", "Please select a PDF file")
            return
        pdf_path = Path(path)
        try:
            extraction = self.extractor.process_pdf(pdf_path)
            parse_result = self.parser.parse(extraction)
            self.current_result = (extraction, parse_result)
            self._render_results(extraction.to_json(), parse_result)
            if self.auto_sync_checkbox.isChecked():
                self._sync_to_sheets(parse_result)
        except FileNotFoundError:
            QMessageBox.critical(self, "File not found", "Selected file does not exist")
        except Exception as exc:
            logger.exception("Failed to process PDF", error=str(exc))
            QMessageBox.critical(self, "Processing error", str(exc))

    def _render_results(self, extraction_text: str, parse_result) -> None:
        self.extraction_output.setPlainText(extraction_text)
        self.entity_table.setRowCount(0)
        fields = [
            ("Vendor", parse_result.vendor),
            ("Invoice ID", parse_result.invoice_id),
            ("Invoice Date", parse_result.invoice_date),
            ("Total", parse_result.total),
        ]
        for label, field in fields:
            if field:
                self._add_entity_row(label, field.value, field.confidence, field.source, field.reasoning)
        for entity in parse_result.additional_entities:
            self._add_entity_row(entity.name, entity.value, entity.confidence, entity.source, entity.reasoning)
        self.reasoning_view.clear()
        for step in parse_result.reasoning_steps:
            item = QListWidgetItem(f"{step.get('field')}: {step.get('detail')} ({step.get('method')})")
            self.reasoning_view.addItem(item)

    def _add_entity_row(self, name: str, value: str, confidence: float, source: str, reasoning: str) -> None:
        row = self.entity_table.rowCount()
        self.entity_table.insertRow(row)
        self.entity_table.setItem(row, 0, QTableWidgetItem(name))
        self.entity_table.setItem(row, 1, QTableWidgetItem(value))
        self.entity_table.setItem(row, 2, QTableWidgetItem(f"{confidence:.2f}"))
        item = QTableWidgetItem(source)
        item.setToolTip(reasoning)
        self.entity_table.setItem(row, 3, item)

    @Slot()
    def _save_settings(self) -> None:
        settings = {
            **self._settings_data,
            "auto_sync": self.auto_sync_checkbox.isChecked(),
            "confidence_mode": self.settings_confidence_mode.currentText(),
        }
        self._settings_data = settings
        try:
            self._persist_settings()
        except Exception:
            return
        QMessageBox.information(self, "Saved", "Settings saved successfully")
        logger.info("Settings saved", settings=settings)

    def _persist_settings(self) -> None:
        try:
            self.settings_path.write_text(json.dumps(self._settings_data, indent=2))
        except Exception as exc:
            logger.exception("Failed to save settings", error=str(exc))
            QMessageBox.critical(self, "Error", "Unable to save settings")
            raise

    def _load_settings(self) -> None:
        if not self.settings_path.exists():
            logger.warning("Settings file missing; using defaults", path=str(self.settings_path))
            return
        try:
            settings = json.loads(self.settings_path.read_text())
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse settings", error=str(exc))
            return
        self._settings_data = settings
        self.auto_sync_checkbox.setChecked(settings.get("auto_sync", True))
        mode = settings.get("confidence_mode", "balanced")
        self.settings_confidence_mode.setCurrentText(mode)
        self.confidence_mode.setCurrentText(mode)
        logger.debug("Settings loaded", settings=settings)

    def _sync_to_sheets(self, parse_result) -> None:
        if parse_result.invoice_id is None:
            logger.warning("Skipping Sheets sync without invoice ID")
            return
        record = {
            "uid": parse_result.invoice_id.value,
            "vendor": parse_result.vendor.value if parse_result.vendor else "",
            "invoice_date": parse_result.invoice_date.value if parse_result.invoice_date else "",
            "total": parse_result.total.value if parse_result.total else "",
        }
        success = self.sheet_sync.upsert_records([record])
        if success:
            logger.info("Synced record to Sheets", uid=record["uid"])
        else:
            logger.error("Failed to sync record to Sheets", uid=record["uid"])

    @Slot()
    def _submit_feedback(self) -> None:
        if not self.current_result:
            QMessageBox.warning(self, "No result", "Process a PDF before submitting feedback")
            return
        feedback_text = self.feedback_input.toPlainText().strip()
        if not feedback_text:
            QMessageBox.warning(self, "Empty feedback", "Please provide feedback text")
            return
        extraction, parse_result = self.current_result
        payload = {
            "feedback": feedback_text,
            "invoice_id": parse_result.invoice_id.value if parse_result.invoice_id else None,
        }
        self.training_engine.record_feedback(payload)
        QMessageBox.information(self, "Thank you", "Feedback recorded")
        self.feedback_input.clear()


def launch_app(settings_path: Path, known_entities_path: Path) -> None:  # pragma: no cover - GUI entry
    if QApplication is None:
        raise RuntimeError("PySide6 is required to run the GUI. Please install PySide6.")
    app = QApplication([])
    window = InvoiceMainWindow(settings_path, known_entities_path)
    window.show()
    logger.info("Launching GUI")
    app.exec()


__all__ = ["launch_app", "InvoiceMainWindow"]
