"""
Shared utility functions for GOJEP scrapers.
"""
from __future__ import annotations

import re
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.gojep.gov.jm"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; JamaicaProcurementBot/1.0; "
        "research use)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

logger = logging.getLogger(__name__)


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def fetch_page(
    session: requests.Session,
    url: str,
    delay: float = 1.5,
    retries: int = 3,
) -> Optional[BeautifulSoup]:
    time.sleep(delay)
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(delay * attempt * 2)
    logger.error("All retries exhausted for %s", url)
    return None


def clean_amount(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def clean_text(raw: str) -> str:
    return " ".join(raw.split()) if raw else ""


CATEGORY_TAXONOMY = {
    "Roads & Infrastructure": ["road", "highway", "bridge", "drainage", "asphalt", "pavement", "rehabilitation", "infrastructure", "culvert"],
    "Medical & Health": ["hospital", "clinic", "medical", "pharmaceutical", "drug", "medicine", "health", "clinical", "laboratory", "ambulance", "surgical", "vaccine", "patient"],
    "Cleaning & Sanitation": ["cleaning", "janitorial", "sanitation", "hygiene", "pest", "garbage", "waste", "portering", "laundry", "laundering"],
    "Security Services": ["security", "guard", "patrol", "surveillance", "cctv", "access control", "alarm"],
    "IT & Technology": ["software", "hardware", "computer", "laptop", "server", "network", "technology", "system", "license", "microsoft", "cisco", "firewall", "digital", "database", "nessus", "fortinet"],
    "Construction & Works": ["construction", "building", "renovation", "retrofit", "plumbing", "electrical", "staircase", "roofing", "fence", "painting"],
    "Consultancy & Professional": ["consultant", "consultancy", "advisory", "audit", "legal", "accounting", "architect", "engineer", "design", "survey", "research"],
    "Office Supplies & Furniture": ["office", "stationery", "furniture", "chair", "desk", "printer", "toner", "paper"],
    "Food & Provisions": ["food", "provision", "catering", "meal", "nutrition", "grocery", "beverage", "lunch"],
    "Vehicles & Transport": ["vehicle", "bus", "truck", "car", "fleet", "transport", "tyre", "motorcycle", "fuel", "gasoline"],
    "Utilities": ["electricity", "solar", "energy", "utility", "gas", "industrial gas"],
    "Training & Education": ["training", "workshop", "seminar", "education", "capacity", "development", "scholarship"],
}


def normalise_category(title: str) -> str:
    if not title:
        return "Other"
    lower = title.lower()
    for category, keywords in CATEGORY_TAXONOMY.items():
        for kw in keywords:
            if kw in lower:
                return category
    return "Other"
