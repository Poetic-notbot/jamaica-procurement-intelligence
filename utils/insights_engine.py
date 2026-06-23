"""
Insights Engine - Jamaica Procurement OS
Rules-based auto-insight generator. No AI required.
Produces narrative insights from procurement data.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_insights(awards_df: pd.DataFrame, bids_df: pd.DataFrame) -> list:
    """Return a list of insight dicts with keys: type, icon, headline, detail, severity."""
    insights = []
    now = datetime.now()

    if awards_df is None or awards_df.empty:
        return [{"type":"info","icon":"i","headline":"No award data loaded yet.","detail":"Run the scraper to populate data.","severity":"low"}]

    df = awards_df.copy()
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd", 0), errors="coerce").fillna(0)

    # Parse dates
    if "publication_date" in df.columns:
        df["pub_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
        df["year_month"] = df["pub_date"].dt.to_period("M")
        df["quarter"] = df["pub_date"].dt.to_period("Q")

    total_value = df["contract_amount_jmd"].sum()
    total_awards = len(df)

    # --- INSIGHT 1: Total platform value ---
    if total_value > 0:
        val_b = total_value / 1e9
        insights.append({
            "type": "kpi", "icon": "JMD",
            "headline": "JMD ${:.1f}B in contract awards tracked".format(val_b),
            "detail": "Across {:,} contracts on the platform.".format(total_awards),
            "severity": "neutral"
        })

    # --- INSIGHT 2: Top category by value ---
    if "normalized_category" in df.columns:
        cat_val = df.groupby("normalized_category")["contract_amount_jmd"].sum().sort_values(ascending=False)
        if not cat_val.empty:
            top_cat = cat_val.index[0]
            top_pct = (cat_val.iloc[0] / total_value * 100) if total_value > 0 else 0
            insights.append({
                "type": "category", "icon": "CAT",
                "headline": "{} accounts for {:.0f}% of all awards by value".format(top_cat, top_pct),
                "detail": "JMD ${:.1f}M in {} contracts.".format(cat_val.iloc[0]/1e6, (df["normalized_category"]==top_cat).sum()),
                "severity": "high"
            })

    # --- INSIGHT 3: Top buyer by spend ---
    if "procuring_entity" in df.columns:
        buyer_val = df.groupby("procuring_entity")["contract_amount_jmd"].sum().sort_values(ascending=False)
        if not buyer_val.empty:
            top_buyer = buyer_val.index[0]
            insights.append({
                "type": "buyer", "icon": "BUY",
                "headline": "{} is the top spending entity".format(top_buyer[:50]),
                "detail": "JMD ${:.1f}M in total awards.".format(buyer_val.iloc[0]/1e6),
                "severity": "high"
            })

    # --- INSIGHT 4: Recent activity surge (last 90 days) ---
    if "pub_date" in df.columns:
        cutoff = pd.Timestamp(now - timedelta(days=90))
        recent = df[df["pub_date"] >= cutoff]
        if len(recent) > 0:
            recent_val = recent["contract_amount_jmd"].sum()
            insights.append({
                "type": "trend", "icon": "TRD",
                "headline": "{:,} awards in the last 90 days".format(len(recent)),
                "detail": "Worth JMD ${:.1f}M.".format(recent_val/1e6),
                "severity": "medium"
            })

    # --- INSIGHT 5: Quarter-over-quarter change ---
    if "quarter" in df.columns:
        q_counts = df.groupby("quarter").size()
        if len(q_counts) >= 2:
            last_q = q_counts.iloc[-1]
            prev_q = q_counts.iloc[-2]
            pct_change = ((last_q - prev_q) / prev_q * 100) if prev_q > 0 else 0
            direction = "increased" if pct_change > 0 else "decreased"
            insights.append({
                "type": "trend", "icon": "QoQ",
                "headline": "Award volume {} {:.0f}% quarter-over-quarter".format(direction, abs(pct_change)),
                "detail": "{} awards last quarter vs {} prior quarter.".format(last_q, prev_q),
                "severity": "high" if abs(pct_change) > 20 else "medium"
            })

    # --- INSIGHT 6: Supplier concentration ---
    if "supplier_name" in df.columns:
        df_sup = df[df["supplier_name"].notna() & (df["supplier_name"] != "")]
        if len(df_sup) > 0:
            sup_counts = df_sup.groupby("supplier_name").size().sort_values(ascending=False)
            top_supplier = sup_counts.index[0]
            top_count = sup_counts.iloc[0]
            insights.append({
                "type": "supplier", "icon": "SUP",
                "headline": "{} leads with {:,} contract wins".format(top_supplier[:50], top_count),
                "detail": "Top supplier by award count.",
                "severity": "medium"
            })

    # --- INSIGHT 7: Open bids closing soon ---
    if bids_df is not None and not bids_df.empty:
        bdf = bids_df.copy()
        bdf["deadline"] = pd.to_datetime(bdf.get("submission_deadline", pd.Series()), errors="coerce")
        upcoming = bdf[bdf["deadline"] >= pd.Timestamp(now)]
        upcoming = upcoming[bdf["deadline"] <= pd.Timestamp(now + timedelta(days=14))]
        if len(upcoming) > 0:
            insights.append({
                "type": "opportunity", "icon": "OPP",
                "headline": "{} bids closing in the next 14 days".format(len(upcoming)),
                "detail": "Review opportunities before deadlines.",
                "severity": "high"
            })

    # --- INSIGHT 8: Low competition categories ---
    if "normalized_category" in df.columns and "procurement_method" in df.columns:
        sole_source = df[df["procurement_method"].str.contains("sole|direct|limited", case=False, na=False)]
        if len(sole_source) > 0:
            ss_pct = len(sole_source) / len(df) * 100
            insights.append({
                "type": "competition", "icon": "CPT",
                "headline": "{:.0f}% of awards used non-competitive methods".format(ss_pct),
                "detail": "Sole source / direct / limited tendering detected.",
                "severity": "medium"
            })

    return insights
