#!/usr/bin/env python3
"""
CLI entry-point - scrapes GOJEP and stores results in SQLite.

Usage:
    python run_scrapers.py                 # scrape both
    python run_scrapers.py --awards        # only awards
    python run_scrapers.py --bids          # only bids
    python run_scrapers.py --pages 200     # 200 pages each
"""
from __future__ import annotations
import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scrapers")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.awards_scraper import scrape_awards
from scrapers.bids_scraper import scrape_bids
from database.db import init_db, get_engine, upsert_bid


def main():
    parser = argparse.ArgumentParser(description="Scrape GOJEP data into SQLite")
    parser.add_argument("--awards", action="store_true")
    parser.add_argument("--bids", action="store_true")
    parser.add_argument("--pages", type=int, default=int(os.getenv("MAX_PAGES", "50")),
                        help="Max pages per source (default 50)")
    args = parser.parse_args()

    run_awards = args.awards or (not args.awards and not args.bids)
    run_bids = args.bids or (not args.awards and not args.bids)

    init_db()
    engine = get_engine()

    if run_awards:
        logger.info("=== Scraping Contract Award Notices ===")
        summary = scrape_awards(max_pages=args.pages)
        logger.info("Awards done: %s", summary)

    if run_bids:
        logger.info("=== Scraping Opened Bid Competitions ===")
        records = scrape_bids(max_pages=args.pages)
        with engine.begin() as conn:
            for r in records:
                upsert_bid(conn, r)
        logger.info("Saved %d bid records", len(records))

    logger.info("Done. DB: %s", os.getenv("DB_PATH", "procurement.db"))


if __name__ == "__main__":
    main()
