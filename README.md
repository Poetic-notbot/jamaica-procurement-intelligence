# Jamaica Procurement Intelligence

A Streamlit dashboard for exploring Jamaica public procurement data from [GOJEP](https://www.gojep.gov.jm/epps/).

## Live App

[**View Live Dashboard**](https://share.streamlit.io) *(URL will appear after deployment)*

## What Does This App Do?

This app collects and visualises contract award notices and opened bid competitions published by the Government of Jamaica Electronic Procurement (GOJEP) portal. It helps suppliers, researchers, and analysts understand:

- Which government agencies are spending the most
- What categories of goods and services are being procured
- Price benchmarks for specific categories
- Upcoming open bid opportunities
- Seasonal purchasing patterns by buyer

## Quick Start

### Step 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Run the dashboard (uses built-in sample data immediately)
```bash
streamlit run dashboard/app.py
```

### Step 3 — Scrape live data (optional)
```bash
python run_scrapers.py
```

This scrapes up to 50 pages (approximately 500 records) from each data source.
To scrape more pages:
```bash
python run_scrapers.py --pages 200
```

## Project Structure

```
jamaica-procurement-intelligence/
├── dashboard/
│   └── app.py               # Streamlit dashboard (main entry point)
├── scrapers/
│   ├── awards_scraper.py    # Scraper for contract award notices
│   └── bids_scraper.py      # Scraper for opened bid competitions
├── database/
│   └── db.py                # SQLite database layer
├── data/
│   ├── sample_awards.csv    # Sample award data (works without scraping)
│   └── sample_bids.csv      # Sample bids data (works without scraping)
├── utils/
│   └── helpers.py           # Shared utilities + category taxonomy
├── .streamlit/
│   └── config.toml          # Streamlit theme configuration
├── requirements.txt         # Python dependencies
├── run_scrapers.py          # CLI to run scrapers
└── README.md                # This file
```

## Data Sources

| Source | URL |
|--------|-----|
| Contract Award Notices | https://www.gojep.gov.jm/epps/viewCaNotices.do |
| Opened Bid Competitions | https://www.gojep.gov.jm/epps/common/viewOpenedTenders.do |

**Note:** Only public, non-login-gated pages are scraped. The scraper uses a 1.5-second delay between requests to be polite to the server.

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| Overview | KPI cards, awards by month, procurement method breakdown |
| Awards | Full searchable awards table with price band chart |
| Buyers | Top buyers by value and count, supplier intelligence summary |
| Benchmarks | Min/max/median/average for any buyer + category combination |
| Seasonality | Monthly purchasing frequency and value heatmaps per buyer |
| Open Bids | Recent bid opportunities, deadlines, export to CSV |

## Updating Data

Run the scraper as often as you like:
```bash
# Update both sources
python run_scrapers.py

# Update only awards
python run_scrapers.py --awards

# Update only bids
python run_scrapers.py --bids

# Scrape all pages (full historical data)
python run_scrapers.py --pages 1231
```

The SQLite database (`procurement.db`) will be updated automatically. The dashboard detects the database automatically and reloads data every 5 minutes.

## Redeploying on Streamlit Cloud

1. Push any changes to GitHub
2. Streamlit Cloud will automatically redeploy within a few minutes
3. Or go to https://share.streamlit.io and click "Reboot app"

## Adding New Data Sources

1. Create a new scraper in `scrapers/new_source_scraper.py` following the pattern in `awards_scraper.py`
2. Add a new table definition in `database/db.py`
3. Add a new tab or section in `dashboard/app.py`
4. Update `run_scrapers.py` to call your new scraper

## Troubleshooting

| Problem | Solution |
|---------|----------|
| App shows "No data found" | Run `python run_scrapers.py` or check that `data/` folder contains CSVs |
| Scraper fails with timeout | GOJEP server may be slow; try reducing `--pages` value |
| Import errors | Ensure you run `streamlit run dashboard/app.py` from the project root |
| Streamlit Cloud deployment fails | Check that `requirements.txt` lists all packages and `dashboard/app.py` is set as main file |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `procurement.db` | Path to SQLite database |
| `SCRAPE_DELAY` | `1.5` | Seconds between HTTP requests |
| `MAX_PAGES` | `50` | Default max pages per scrape |

## License

Open source — MIT License. Data sourced from public government portal.
