"""
Scraper for GOJEP Competitions of Opened Bids.
URL: https://www.gojep.gov.jm/epps/common/viewOpenedTenders.do
Pagination: &d-3680181-p=N (confirmed from live page)
"""
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
import time
import requests
from bs4 import BeautifulSoup
from utils.helpers import classify_category, make_bid_hash

BASE_URL = "https://www.gojep.gov.jm"
TIMEOUT = float(os.getenv("SCRAPE_TIMEOUT", "30"))
USER_AGENT = os.getenv(
    "SCRAPE_UA",
    "Mozilla/5.0 (compatible; JamaicaProcurementOS/1.0; +bids-archiver)",
)


def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})
    return s


def fetch_page(session: requests.Session, url: str, delay: float = 1.5):
    try:
        time.sleep(delay)
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as exc:
        logging.getLogger(__name__).warning("fetch failed for %s : %s", url, exc)
        return None

def clean_text(raw) -> str:
    """Strip whitespace from a string value."""
    return str(raw or "").strip()




logger = logging.getLogger(__name__)
BIDS_BASE = (
    f"{BASE_URL}/epps/common/viewOpenedTenders.do"
    "?selectedItem=common%2FviewOpenedTenders.do"
)
PAGE_PARAM = "d-3680181-p"
DELAY = float(os.getenv("SCRAPE_DELAY", "1.5"))


def _parse_page(soup) -> list[dict]:
    table = soup.find("table", {"id": "T01"})
    if not table:
        content = soup.find("div", {"id": "Content"})
        table = content.find("table") if content else soup.find("table")
    if not table:
        return []
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    records = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 7:
            continue
        title_a = cols[1].find("a")
        title = clean_text(title_a.get_text()) if title_a else clean_text(cols[1].get_text())
        href = title_a.get("href", "") if title_a else ""
        source_url = (BASE_URL + href) if href.startswith("/") else href
        reference = clean_text(cols[2].get_text())
        pe = clean_text(cols[3].get_text())
        deadline = clean_text(cols[4].get_text())
        proc_method = clean_text(cols[5].get_text())
        bids_a = cols[6].find("a")
        bids_href = bids_a.get("href", "") if bids_a else ""
        bids_url = (BASE_URL + bids_href) if bids_href.startswith("/") else bids_href
        status = clean_text(cols[8].get_text()) if len(cols) > 8 else ""
        if not title:
            continue
        records.append({
            "cft_title": title,
            "reference_number": reference,
            "procuring_entity": pe,
            "submission_deadline": deadline,
            "procurement_method": proc_method,
            "status": status,
            "opened_bids_url": bids_url or None,
            "source_url": source_url or BIDS_BASE,
            "category": classify_category(title),
            "scraped_at": datetime.now(timezone.utc),
        })
    return records


def scrape_bids(max_pages: int = 50) -> list[dict]:
    session = get_session()
    all_records = []
    seen = set()
    logger.info("Starting bids scrape - max %d pages", max_pages)
    for page_num in range(1, max_pages + 1):
        url = BIDS_BASE if page_num == 1 else f"{BIDS_BASE}&{PAGE_PARAM}={page_num}"
        logger.info("  Bids page %d: %s", page_num, url)
        soup = fetch_page(session, url, delay=DELAY)
        if soup is None:
            break
        records = _parse_page(soup)
        if not records:
            break
        for r in records:
            key = r["reference_number"] or r["cft_title"]
            if key not in seen:
                seen.add(key)
                all_records.append(r)
        logger.info("  Page %d: total so far %d", page_num, len(all_records))
        if not soup.find("button", title="Next"):
            break
    logger.info("Bids scrape done. Total: %d", len(all_records))
    return all_records
