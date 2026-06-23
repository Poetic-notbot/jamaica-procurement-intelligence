"""
Scraper for GOJEP Contract Award Notices.

Source : https://www.gojep.gov.jm/epps/viewCaNotices.do  (public, no CAPTCHA)
Paging : ?d-16531-p=N&selectedItem=viewCaNotices.do  (Apache displaytag)

Self-contained: owns its HTTP session + HTML parsing, persists rows into the
contract_awards table via database.db.upsert_award, and records each run in a
scraper_runs table (created on demand) so the dashboard can show last-run
status instead of "No scraper runs logged".
"""
from __future__ import annotations

import os
import re
import time
import json
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

from utils.helpers import clean_amount, classify_category, make_award_hash
from database.db import get_engine, init_db, upsert_award

logger = logging.getLogger(__name__)

BASE_URL    = "https://www.gojep.gov.jm"
AWARDS_URL  = BASE_URL + "/epps/viewCaNotices.do"
PAGE_PARAM  = "d-16531-p"          # displaytag page index (confirmed live)
SELECTED    = "viewCaNotices.do"   # nav-context param required for table render
DELAY       = float(os.getenv("SCRAPE_DELAY", "1.5"))
TIMEOUT     = float(os.getenv("SCRAPE_TIMEOUT", "30"))
USER_AGENT  = os.getenv(
    "SCRAPE_UA",
    "Mozilla/5.0 (compatible; JamaicaProcurementOS/1.0; +award-archiver)",
)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})
    return s


def _page_url(page_num: int) -> str:
    return f"{AWARDS_URL}?{PAGE_PARAM}={page_num}&selectedItem={SELECTED}"


def fetch_soup(session: requests.Session, url: str):
    try:
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch failed for %s : %s", url, exc)
        return None


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _clean(textval) -> str:
    return " ".join((textval or "").split()).strip()


def _total_results(soup) -> "int | None":
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"([\d,]+)\s+results in total", txt)
    return int(m.group(1).replace(",", "")) if m else None


def _parse_page(soup) -> list:
    table = soup.find("table", {"id": "T01"}) or soup.find("table")
    if not table:
        return []
    body = table.find("tbody") or table
    records = []
    for row in body.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 6:
            continue
        pe          = _clean(cols[2].get_text())
        title_a     = cols[3].find("a")
        title       = _clean(title_a.get_text()) if title_a else _clean(cols[3].get_text())
        if not title:
            continue
        href        = (title_a.get("href", "") if title_a else "") or ""
        source_url  = (BASE_URL + href) if href.startswith("/") else (href or AWARDS_URL)
        pdf_url     = None
        if len(cols) > 6:
            pdf_a = cols[6].find("a")
            if pdf_a and pdf_a.get("href"):
                ph = pdf_a["href"]
                pdf_url = (BASE_URL + ph) if ph.startswith("/") else ph
        pub_date             = _clean(cols[5].get_text())
        category, confidence = classify_category(title)
        records.append({
            "procurement_method":  _clean(cols[1].get_text()),
            "procuring_entity":    pe,
            "title":               title,
            "contract_amount_jmd": clean_amount(cols[4].get_text()),
            "publication_date":    pub_date,
            "notice_pdf_url":      pdf_url,
            "source_url":          source_url,
            "normalized_category": category,
            "category_confidence": confidence,
            "supplier_name":       None,
            "scraped_at":          datetime.now(timezone.utc),
            "data_hash":           make_award_hash(pe, title, pub_date),
        })
    return records


# --------------------------------------------------------------------------- #
# Run logging (self-provisioning table; no schema change needed elsewhere)
# --------------------------------------------------------------------------- #
def _ensure_runs_table(conn):
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS scraper_runs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, status TEXT, "
        "pages_fetched INTEGER, rows_seen INTEGER, rows_new INTEGER, "
        "total_available INTEGER, error TEXT, finished_at TEXT)"
    ))


def _log_run(engine, summary: dict):
    try:
        with engine.begin() as conn:
            _ensure_runs_table(conn)
            conn.execute(text(
                "INSERT INTO scraper_runs "
                "(source,status,pages_fetched,rows_seen,rows_new,total_available,error,finished_at) "
                "VALUES (:source,:status,:pages_fetched,:rows_seen,:rows_new,"
                ":total_available,:error,:finished_at)"
            ), summary)
    except Exception:  # noqa: BLE001
        logger.exception("could not log scraper run")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def scrape_awards(max_pages: int = 50, persist: bool = True) -> dict:
    """
    Walk Contract Award Notices pages, upsert into contract_awards, log the run.

    Stops when a page yields no rows, when every advertised result has been
    collected, or when max_pages is reached. Returns a summary dict.
    """
    session = get_session()
    engine = None
    if persist:
        init_db()
        engine = get_engine()

    seen_hashes = set()
    rows_seen = rows_new = pages_fetched = 0
    total_available = None
    status, error = "success", None

    try:
        for page_num in range(1, max_pages + 1):
            soup = fetch_soup(session, _page_url(page_num))
            if soup is None:
                if page_num == 1:
                    status, error = "error", "first page fetch failed"
                break
            if total_available is None:
                total_available = _total_results(soup)

            records = _parse_page(soup)
            if not records:
                break
            pages_fetched += 1

            batch = []
            for r in records:
                h = r["data_hash"]
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    rows_seen += 1
                    batch.append(r)

            if persist and batch:
                with engine.begin() as conn:
                    hashes = [r["data_hash"] for r in batch]
                    placeholders = ",".join(f":h{i}" for i in range(len(hashes)))
                    params = {f"h{i}": h for i, h in enumerate(hashes)}
                    existing = conn.execute(
                        text(f"SELECT data_hash FROM contract_awards "
                             f"WHERE data_hash IN ({placeholders})"),
                        params,
                    ).fetchall()
                    already = {row[0] for row in existing}
                    for r in batch:
                        if r["data_hash"] not in already:
                            rows_new += 1
                        upsert_award(conn, r)

            logger.info("page %d | seen=%d new=%d", page_num, rows_seen, rows_new)

            if total_available and rows_seen >= total_available:
                break
            time.sleep(DELAY)
    except Exception as exc:  # noqa: BLE001
        status, error = "error", str(exc)
        logger.exception("awards scrape failed")

    summary = {
        "source":          "contract_award_notices",
        "status":          status,
        "pages_fetched":   pages_fetched,
        "rows_seen":       rows_seen,
        "rows_new":        rows_new,
        "total_available": total_available,
        "error":           error,
        "finished_at":     datetime.now(timezone.utc).isoformat(),
    }
    if persist and engine is not None:
        _log_run(engine, summary)
    logger.info("awards scrape finished: %s", json.dumps(summary, default=str))
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    print(scrape_awards(max_pages=int(os.getenv("MAX_PAGES", "50"))))
