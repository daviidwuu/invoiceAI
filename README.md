# InvoiceAI

InvoiceAI is a desktop workflow for extracting data from invoice PDFs, parsing key business fields with local AI models, and synchronising results to Google Sheets. The project also captures user feedback to drive incremental training of local models.

## Features

- **Hybrid Extraction** – Automatically selects between native PDF text extraction and OCR (Tesseract) while capturing snippets and bounding boxes.
- **Local Parsing** – Runs configurable local NLP models or rule-based heuristics to detect entities, provide reasoning metadata, and manage confidence scoring.
- **Google Sheets Sync** – Authenticates with a service account, enforces UID uniqueness, applies locking, and retries operations to handle API quotas.
- **Feedback-Driven Training** – Stores feedback in JSONL, logs training runs, and versions incremental models.
- **Rich GUI & CLI** – PySide6 interface for visual workflows plus a headless CLI that outputs tab-separated invoice rows for spreadsheet ingestion.
- **Rich GUI** – PySide6 interface with Dashboard, Settings, and Training tabs that surface confidence information and explainability context.

## Repository Structure

```
extract/               # PDF and OCR extraction
parse/                 # Local AI parsing logic
sheets/                # Google Sheets integration
training/              # Incremental training engine
gui/                   # PySide6 GUI application
config/                # User settings, credentials template, known entities
models/                # Local model versions (created during training)
logs/                  # Application and training logs
training_data/         # Captured feedback samples
sample_assets/         # Example PDFs for testing
```

## Quick Start

1. **Create and activate a virtual environment.**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\\Scripts\\activate   # Windows
   ```

2. **Install dependencies.**
   ```bash
   pip install -r requirements.txt
   ```
   If you do not have a `requirements.txt` yet, install the core libraries manually:
   ```bash
   pip install loguru pdfplumber pdf2image pytesseract PySide6 gspread google-auth
   ```
   OCR features require `poppler` for `pdf2image` and Tesseract OCR runtime to be installed on your system.

3. **Configure Google Sheets access.**
   - Copy `config/credentials_template.json` to `config/credentials.json` and populate it with your Google Cloud service account details.
   - Share the target spreadsheet with the service-account email address.

4. **Launch the application.**
   ```bash
   python main.py
   ```
   The GUI will open with Dashboard, Settings, and Training tabs. Load a PDF using the Dashboard to run extraction and parsing.

## Sample Data

Use the sample invoice located at `sample_assets/sample_invoice.pdf` to validate extraction, parsing, and Sheets synchronisation (offline mode). Additional test assets can be added to the `sample_assets/` directory.

## Feedback and Training

- Feedback submitted through the Training tab is appended to `training_data/feedback.jsonl`.
- Each training run appends metadata to `logs/training_history.csv` and stores a versioned model directory under `models/`.

## Logging

Loguru writes application logs to `logs/app.log`. Review the file for troubleshooting (OCR fallback, Sheets errors, missing credentials, etc.).

## Development Notes

- The system gracefully degrades if optional dependencies (e.g., spaCy, gspread) are unavailable, logging actionable messages.
- Parsing logic prefers known vendors defined in `config/known_entities.json` and falls back to regex heuristics.
- Extend the parser by loading alternative local models via the Settings tab (`selected_model` setting).

## Testing

For automated testing, create unit tests that target the `extract`, `parse`, and `training` packages. Sample PDFs in `sample_assets/` can be used to seed fixture data.

## License

This project is provided as-is for demonstration purposes.
