"""
analytics.py — Advanced Analytics Engine
Features 5-10: Win Rate, Geo-Intelligence, Similar Tender Finder,
Budget Cycle Predictor, Multi-Source Stubs, Relationship Graph.
"""
from __future__ import annotations
import re, math, logging
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# FEATURE 5 — BID WIN RATE CALCULATOR
# ─────────────────────────────────────────────────────────────

def compute_win_rates(awards_df: pd.DataFrame, bids_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cross-reference suppliers appearing in bids vs awards.
    Returns DataFrame: supplier, bids_entered, contracts_won, win_rate_pct, total_value_won
    """
    rows = []
    # Build supplier -> award count from awards
    award_counts = {}
    award_values = {}
    if "supplier_name" in awards_df.columns:
        for name, grp in awards_df.groupby("supplier_name"):
            if pd.isna(name) or str(name).strip() == "":
                continue
            award_counts[str(name).strip()] = len(grp)
            award_values[str(name).strip()] = pd.to_numeric(grp.get("contract_amount_jmd", pd.Series()), errors="coerce").sum()
    # Build supplier -> bid count from bids extracted names
    bid_counts = {}
    if "supplier_names_extracted" in bids_df.columns:
        for _, row in bids_df.iterrows():
            names_str = str(row.get("supplier_names_extracted","") or "")
            for name in names_str.split(","):
                name = name.strip()
                if name:
                    bid_counts[name] = bid_counts.get(name, 0) + 1
    # Union of all known suppliers
    all_suppliers = set(award_counts.keys()) | set(bid_counts.keys())
    for sup in sorted(all_suppliers):
        won  = award_counts.get(sup, 0)
        bid  = bid_counts.get(sup, 0)
        total_known = max(won, bid)
        win_rate = (won / total_known * 100) if total_known > 0 else None
        rows.append({
            "supplier":        sup,
            "bids_entered":    bid,
            "contracts_won":   won,
            "win_rate_pct":    round(win_rate, 1) if win_rate is not None else None,
            "total_value_won": award_values.get(sup, 0.0),
        })
    return pd.DataFrame(rows).sort_values("total_value_won", ascending=False)


# ─────────────────────────────────────────────────────────────
# FEATURE 6 — GEO-INTELLIGENCE: PARISH MAPPING
# ─────────────────────────────────────────────────────────────

PARISH_KEYWORDS: Dict[str, List[str]] = {
    "Kingston":           ["kingston","ksw","kinwor","central kingston"],
    "St. Andrew":         ["st andrew","half way tree","papine","liguanea","constant spring","stony hill","port antonio"],
    "St. Thomas":         ["st thomas","morant bay","yallahs","bath"],
    "Portland":           ["portland","port antonio","buff bay"],
    "St. Mary":           ["st mary","annotto bay","port maria","highgate"],
    "St. Ann":            ["st ann","ocho rios","brown town","st anns bay"],
    "Trelawny":           ["trelawny","falmouth","clark town"],
    "St. James":          ["st james","montego bay","mob","rose hall"],
    "Hanover":            ["hanover","lucea","green island"],
    "Westmoreland":       ["westmoreland","savanna-la-mar","negril","bluefields"],
    "St. Elizabeth":      ["st elizabeth","black river","junction","santa cruz"],
    "Manchester":         ["manchester","mandeville","christiana"],
    "Clarendon":          ["clarendon","may pen","chapelton","lionel town"],
    "St. Catherine":      ["st catherine","spanish town","portmore","old harbour","linstead"],
    "Kingston Metropolitan": ["nwc","nht","mof","moh","ksac","portia simpson","parliament","national works"],
}

ENTITY_PARISH_MAP: Dict[str, str] = {
    "national water commission":        "Kingston Metropolitan",
    "national housing trust":           "Kingston Metropolitan",
    "ministry of finance":              "Kingston Metropolitan",
    "ministry of health":               "Kingston Metropolitan",
    "ministry of education":            "Kingston Metropolitan",
    "ministry of national security":    "Kingston Metropolitan",
    "heart nsta trust":                 "Kingston Metropolitan",
    "urban development corporation":    "Kingston Metropolitan",
    "development bank of jamaica":      "Kingston Metropolitan",
    "jamaica public service":           "Kingston Metropolitan",
    "works and public infrastructure":  "Kingston Metropolitan",
    "parish council":                   "St. Catherine",
}

def map_entity_to_parish(entity: str) -> str:
    """Map a procuring entity name to a Jamaican parish."""
    if not entity:
        return "Unknown"
    lower = entity.lower()
    # Exact-ish entity lookup first
    for key, parish in ENTITY_PARISH_MAP.items():
        if key in lower:
            return parish
    # Keyword scan
    for parish, keywords in PARISH_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return parish
    return "Unknown"

def add_parish_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add parish column to awards or bids DataFrame."""
    df = df.copy()
    if "procuring_entity" in df.columns:
        df["parish"] = df["procuring_entity"].apply(map_entity_to_parish)
    return df

def geo_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return parish-level spend summary."""
    df = add_parish_column(df)
    if "parish" not in df.columns:
        return pd.DataFrame()
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd", 0), errors="coerce").fillna(0)
    return df.groupby("parish").agg(
        award_count=("id","count"),
        total_value=("contract_amount_jmd","sum"),
        unique_buyers=("procuring_entity","nunique"),
    ).sort_values("total_value", ascending=False).reset_index()


# ─────────────────────────────────────────────────────────────
# FEATURE 7 — SIMILAR TENDER FINDER (TF-IDF)
# ─────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text).lower())
    return [t for t in text.split() if len(t) > 2]

def _tfidf_similarity(query: str, documents: List[str]) -> List[float]:
    """Lightweight TF-IDF cosine similarity without sklearn."""
    all_docs = [query] + documents
    # Build term-doc frequency matrix
    all_tokens = [_tokenize(d) for d in all_docs]
    vocab = list(set(t for tokens in all_tokens for t in tokens))
    n_docs = len(all_docs)
    # IDF
    idf = {}
    for term in vocab:
        df_count = sum(1 for tokens in all_tokens if term in tokens)
        idf[term] = math.log((n_docs + 1) / (df_count + 1)) + 1
    # TF-IDF vectors
    def vec(tokens):
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        n = len(tokens) or 1
        return {t: (c/n) * idf.get(t, 1) for t, c in tf.items()}
    vecs = [vec(t) for t in all_tokens]
    # Cosine similarity of query (index 0) vs each doc
    q_vec = vecs[0]
    scores = []
    for d_vec in vecs[1:]:
        num = sum(q_vec.get(t,0) * d_vec.get(t,0) for t in q_vec)
        denom = (math.sqrt(sum(v**2 for v in q_vec.values())) *
                 math.sqrt(sum(v**2 for v in d_vec.values())))
        scores.append(num / denom if denom > 0 else 0.0)
    return scores

def find_similar_tenders(query: str, awards_df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Find top-N contracts most similar to the query string.
    Returns sliced DataFrame with a similarity_score column.
    """
    if awards_df.empty or "title" not in awards_df.columns:
        return pd.DataFrame()
    df = awards_df.dropna(subset=["title"]).copy()
    titles = df["title"].tolist()
    scores = _tfidf_similarity(query, titles)
    df["similarity_score"] = scores
    return df.nlargest(top_n, "similarity_score")[
        [c for c in ["title","procuring_entity","contract_amount_jmd","publication_date",
                     "normalized_category","supplier_name","similarity_score"] if c in df.columns]
    ]


# ─────────────────────────────────────────────────────────────
# FEATURE 8 — BUDGET CYCLE PREDICTOR
# ─────────────────────────────────────────────────────────────

def predict_next_procurement(buyer: str, category: str,
                              awards_df: pd.DataFrame) -> Dict:
    """
    Predict when a buyer will next procure in a category.
    Uses rolling monthly average to estimate next peak month.
    Returns: {buyer, category, avg_monthly_contracts, peak_months, next_predicted_month, confidence}
    """
    result = {
        "buyer": buyer, "category": category,
        "avg_monthly_contracts": 0,
        "peak_months": [],
        "next_predicted_month": None,
        "confidence": "low",
        "data_points": 0,
    }
    df = awards_df.copy()
    if "procuring_entity" not in df.columns or "publication_date" not in df.columns:
        return result
    df = df[df["procuring_entity"].str.lower().str.contains(buyer.lower(), na=False)]
    if category and category != "All Categories" and "normalized_category" in df.columns:
        df = df[df["normalized_category"] == category]
    if len(df) < 3:
        return result
    df["pub_dt"] = pd.to_datetime(df["publication_date"], errors="coerce")
    df = df.dropna(subset=["pub_dt"])
    result["data_points"] = len(df)
    # Monthly frequency
    df["month_num"] = df["pub_dt"].dt.month
    monthly_cnt = df.groupby("month_num").size()
    avg = monthly_cnt.mean()
    result["avg_monthly_contracts"] = round(avg, 2)
    # Peak months (above average)
    peak = monthly_cnt[monthly_cnt >= avg].index.tolist()
    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    result["peak_months"] = [month_names.get(m, str(m)) for m in sorted(peak)]
    # Next predicted: nearest peak month in future
    now_month = datetime.now().month
    future_peaks = [m for m in sorted(peak) if m > now_month]
    if not future_peaks:
        future_peaks = sorted(peak)  # wrap around to next year
    if future_peaks:
        next_m = future_peaks[0]
        next_year = datetime.now().year if next_m > now_month else datetime.now().year + 1
        result["next_predicted_month"] = "{} {}".format(month_names.get(next_m,"?"), next_year)
    # Confidence based on data volume
    if len(df) >= 20:
        result["confidence"] = "high"
    elif len(df) >= 8:
        result["confidence"] = "medium"
    return result


# ─────────────────────────────────────────────────────────────
# FEATURE 10 — BUYER-SUPPLIER RELATIONSHIP GRAPH
# ─────────────────────────────────────────────────────────────

def build_relationship_graph(awards_df: pd.DataFrame, min_contracts: int = 2) -> pd.DataFrame:
    """
    Build buyer-supplier co-occurrence network.
    Returns edge list: buyer, supplier, contract_count, total_value, categories
    Only includes relationships with >= min_contracts awards.
    """
    if "supplier_name" not in awards_df.columns or "procuring_entity" not in awards_df.columns:
        return pd.DataFrame()
    df = awards_df.dropna(subset=["supplier_name","procuring_entity"]).copy()
    df = df[(df["supplier_name"] != "") & (df["procuring_entity"] != "")]
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd", 0), errors="coerce").fillna(0)
    edges = df.groupby(["procuring_entity","supplier_name"]).agg(
        contract_count=("id","count"),
        total_value=("contract_amount_jmd","sum"),
        categories=("normalized_category", lambda x: ", ".join(x.dropna().unique()[:3])),
    ).reset_index()
    edges.columns = ["buyer","supplier","contract_count","total_value","categories"]
    edges = edges[edges["contract_count"] >= min_contracts]
    return edges.sort_values("total_value", ascending=False)

def detect_repeat_relationships(awards_df: pd.DataFrame, threshold: int = 3) -> pd.DataFrame:
    """Flag buyer-supplier pairs with suspiciously high repeat contracts."""
    edges = build_relationship_graph(awards_df, min_contracts=threshold)
    if edges.empty:
        return edges
    edges["flag"] = edges["contract_count"] >= threshold * 2
    return edges


# ─────────────────────────────────────────────────────────────
# FEATURE 9 — MULTI-SOURCE SCRAPER REGISTRY
# ─────────────────────────────────────────────────────────────

ADDITIONAL_SOURCES = [
    {
        "name":        "National Housing Trust (NHT)",
        "base_url":    "https://www.nht.gov.jm",
        "procurement_url": "https://www.nht.gov.jm/procurement",
        "status":      "stub",
        "notes":       "Check /procurement page for tender notices. No standard table format — requires custom parser.",
    },
    {
        "name":        "National Water Commission (NWC)",
        "base_url":    "https://www.nwcjamaica.com",
        "procurement_url": "https://www.nwcjamaica.com/procurement",
        "status":      "stub",
        "notes":       "Procurement notices published as PDFs. Requires PDF scraping.",
    },
    {
        "name":        "HEART NSTA Trust",
        "base_url":    "https://www.heart-nsta.edu.jm",
        "procurement_url": "https://www.heart-nsta.edu.jm/procurement",
        "status":      "stub",
        "notes":       "Training institution. Active procurement buyer. Separate scraper needed.",
    },
    {
        "name":        "Urban Development Corporation (UDC)",
        "base_url":    "https://www.udcja.com",
        "procurement_url": "https://www.udcja.com/procurement",
        "status":      "stub",
        "notes":       "Real estate and infrastructure. High-value contracts.",
    },
    {
        "name":        "Jamaica Public Service (JPS)",
        "base_url":    "https://www.myjpsco.com",
        "procurement_url": "https://www.myjpsco.com/procurement",
        "status":      "stub",
        "notes":       "Utility company. Major infrastructure buyer.",
    },
]

def get_source_registry() -> pd.DataFrame:
    """Return DataFrame of all known procurement data sources."""
    return pd.DataFrame(ADDITIONAL_SOURCES)
