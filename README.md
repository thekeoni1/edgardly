# Edgardly

A web application for searching and downloading SEC EDGAR filings, with structured XBRL financial data extraction.

## Features

- **Company search** — find any SEC-registered company by ticker or name
- **Filing search** — filter 10-K, 10-Q, 8-K, and other form types by date range
- **Batch download** — download multiple filings at once as HTML or PDF
- **XBRL financial data** — extract structured income statement and balance sheet data across annual and quarterly periods
- **Data export** — export filing metadata to CSV or Excel, and XBRL financials to CSV or Excel
- **Downloads library** — browse and open previously downloaded filings
- **Sanity flags** — automatic checks for negative revenue, balance sheet mismatches, and suspicious zero values

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd edgardly/app

# Create and activate a virtual environment (recommended)
python -m venv env
# Windows:
env\Scripts\activate
# macOS/Linux:
source env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (required for PDF conversion)
playwright install chromium

# Run the app
python app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

## Data Source

All filing data is sourced from the [SEC EDGAR public API](https://www.sec.gov/developer). This tool uses the EDGAR submissions API and XBRL company facts API in accordance with SEC rate-limiting guidelines.

## Disclaimer

This tool is intended for research and informational purposes only. It is not financial advice. Always verify data against official SEC filings before making any investment or business decisions.

## License

MIT — see [LICENSE](LICENSE) for details.
