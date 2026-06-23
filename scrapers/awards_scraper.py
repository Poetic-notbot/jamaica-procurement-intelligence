"""
Scraper for GOJEP Contract Award Notices.
URL: https://www.gojep.gov.jm/epps/viewCaNotices.do
Pagination: ?d-16531-p=N (confirmed from live page)
"""
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from utils.helpers import get_session, fetch_page, clean_amount, clean_text, BASE_URL, normalise_category

logger = logging.getLogger(__name__)
AWARDS_URL = f"{BASE_URL}/epps/viewCaNotices.do"
PAGE_PARAM = "d-16531-p"
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
        if len(cols) < 6:
            continue
        proc_method = clean_text(cols[1].get_text())
        pe = clean_text(cols[2].get_text())
        title_a = cols[3].find("a")
        title = clean_text(title_a.get_text()) if title_a else clean_text(cols[3].get_text())
        href = title_a.get("href", "") if title_a else ""
        source_url = (BASE_URL + href) if href.startswith("/") else href
        amount = clean_amount(cols[4].get_text())
        pub_date = clean_text(cols[5].get_text())
        pdf_url = None
        if len(cols) > 6:
            pdf_a = cols[6].find("a")
            if pdf_a:
                pdf_href = pdf_a.get("href", "")
                pdf_url = (BASE_URL + pdf_href) if pdf_href.startswith("/") else pdf_href
        if not title:
            continue
        records.append({
            "procurement_method": proc_method,
            "procuring_entity": pe,
            "title": title,
            "contract_amount_jmd": amount,
            "publication_date": pub_date,
            "notice_pdf_url": pdf_url,
            "source_url": source_url or AWARDS_URL,
            "category": normalise_category(title),
            "scraped_at": datetime.now(timezone.utc),
        })
    return records


def scrape_awards(max_pages: int = 50) -> list[dict]:
    session = get_session()
    all_records = []
    seen = set()
    logger.info("Starting awards scrape - max %d pages", max_pages)
    for page_num in range(1, max_pages + 1):
        url = AWARDS_URL if page_num == 1 else f"{AWARDS_URL}?{PAGE_PARAM}={page_num}"
        logger.info("  Awards page %d: %s", page_num, url)
        soup = fetch_page(session, url, delay=DELAY)
        if soup is None:
            break
        records = _parse_page(soup)
        if not records:
            break
        for r in records:
            key = (r["title"], r["publication_date"])
            if key not in seen:
                seen.add(key)
                all_records.append(r)
        logger.info("  Page %d: total so far %d", page_num, len(all_records))
        if not soup.find("button", title="Next"):
            break
    logger.info("Awards scrape done. Total: %d", len(all_records))
    return all_records
