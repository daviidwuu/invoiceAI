# InvoiceAI Setup Guide

This guide expands on the quick-start instructions in the repository README and highlights optional dependencies for full functionality.

## Dependencies

| Component | Required Packages | System Requirements |
|-----------|-------------------|----------------------|
| Extraction | `pdfplumber`, `pdf2image`, `pytesseract`, `loguru` | Poppler utilities (`pdftoppm`), Tesseract OCR runtime |
| Parsing | `spaCy` (optional), `loguru` | Download language models with `python -m spacy download en_core_web_sm` |
| Sheets | `gspread`, `google-auth` | Google Cloud service account credentials |
| GUI | `PySide6` | Qt runtime supplied via PySide6 wheel |

Install optional extras individually as needed:

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

## Google Sheets Credentials

1. Create a service account in Google Cloud and grant it access to the desired spreadsheet.
2. Download the JSON key and save it as `config/credentials.json`.
3. Ensure the spreadsheet is shared with the service account email.

## Environment Variables

Set `TESSDATA_PREFIX` if Tesseract data files are stored in a non-standard location.

## Running Headless

For environments without a display server, start the application with a virtual framebuffer (`xvfb-run python main.py`) or run extraction/parsing via custom scripts that reuse the `extract` and `parse` packages directly.

## Troubleshooting

- **Missing fonts in OCR output** – install language packs and verify the `tesseract` binary is on your `PATH`.
- **Sheets authentication errors** – confirm the credentials file matches the template format and that the service account has spreadsheet access.
- **spaCy model loading failures** – ensure the selected model is installed and the `selected_model` field in `config/user_settings.json` is updated accordingly.

## Sample Workflow Script

```python
from pathlib import Path
from extract import Extractor
from parse import InvoiceParser

extractor = Extractor()
parser = InvoiceParser()

result = extractor.process_pdf(Path("sample_assets/sample_invoice.pdf"))
parsed = parser.parse(result)
print(parsed.to_json())
```

Use this script to validate extraction and parsing independently of the GUI.
