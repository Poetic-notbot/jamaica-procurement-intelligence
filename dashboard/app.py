"""
Jamaica Procurement Intelligence - Streamlit Dashboard
Run: streamlit run dashboard/app.py
"""
from __future__ import annotations
import io
import os
import sys
import logging
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Jamaica Procurement Intelligence",
    page_icon="🇯🇲",
    layout="wide",
    initial_sidebar_state="expanded",
)

GOLD = "#F7B731"
GREEN = "#007A3D"
BLACK = "#1A1A1A"

@st.cache_data(ttl=300, show_spinner="Loading data...")
def load_data():
    data_dir = ROOT / "data"
    db_path = ROOT / os.getenv("DB_PATH", "procurement.db")
    awards_df = pd.DataFrame()
    bids_df = pd.DataFrame()

    if db_path.exists():
        try:
            from database.db import load_awards, load_bids
            awards_rows = load_awards()
            bids_rows = load_bids()
            if awards_rows:
                awards_df = pd.DataFrame(awards_rows)
            if bids_rows:
                bids_df = pd.DataFrame(bids_rows)
        except Exception as exc:
            logger.warning("Could not load from DB: %s", exc)

    if awards_df.empty:
        csv_path = data_dir / "sample_awards.csv"
        if csv_path.exists():
            awards_df = pd.read_csv(csv_path)

    if bids_df.empty:
        csv_path = data_dir / "sample_bids.csv"
        if csv_path.exists():
            bids_df = pd.read_csv(csv_path)

    if not awards_df.empty:
        awards_df["contract_amount_jmd"] = pd.to_numeric(
            awards_df["contract_amount_jmd"], errors="coerce"
        )
        awards_df["publication_date"] = pd.to_datetime(
            awards_df["publication_date"], errors="coerce", dayfirst=True
        )
        awards_df["year_month"] = awards_df["publication_date"].dt.to_period("M").astype(str)
        if "category" not in awards_df.columns:
            awards_df["category"] = "Other"

    if not bids_df.empty:
        bids_df["submission_deadline"] = pd.to_datetime(
            bids_df["submission_deadline"], errors="coerce", dayfirst=True
        )
        if "category" not in bids_df.columns:
            bids_df["category"] = "Other"

    return awards_df, bids_df


def fmt_jmd(value):
    if pd.isna(value):
        return "N/A"
    if value >= 1_000_000_000:
        return f"J$ {value/1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"J$ {value/1_000_000:.1f}M"
    return f"J$ {value:,.0f}"


def csv_download_btn(df, label, filename):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    st.download_button(
        label=f"⬇ Export {label} to CSV",
        data=buf.getvalue(),
        file_name=filename,
        mime="text/csv",
    )


def main():
    st.markdown(
        f'<div style="background:{GREEN};padding:16px 24px;border-radius:8px;margin-bottom:8px">'
        f'<h1 style="color:white;margin:0;font-size:1.8rem">🇯🇲 Jamaica Procurement Intelligence</h1>'
        f'<p style="color:{GOLD};margin:4px 0 0">Data sourced from the Government of Jamaica Electronic Procurement (GOJEP) portal</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    awards_df, bids_df = load_data()

    if awards_df.empty and bids_df.empty:
        st.error("No data found. Run python run_scrapers.py to scrape live data, or place sample CSVs in the data/ folder.")
        st.stop()

    # Sidebar filters
    st.sidebar.header("🔍 Filters")
    buyer_query = st.sidebar.text_input("Search by buyer / procuring entity", "")
    kw_query = st.sidebar.text_input("Search by keyword / category", "")

    if not awards_df.empty:
        methods = sorted(awards_df["procurement_method"].dropna().unique())
        sel_methods = st.sidebar.multiselect("Procurement method (awards)", methods, default=methods)
    else:
        sel_methods = []

    st.sidebar.markdown("---")
    data_source = "📦 Sample data" if not Path(ROOT / "procurement.db").exists() else "🗄️ Live database"
    st.sidebar.caption(f"Source: {data_source}. Run python run_scrapers.py to update.")

    # Apply filters
    filt_awards = awards_df.copy() if not awards_df.empty else pd.DataFrame()
    filt_bids = bids_df.copy() if not bids_df.empty else pd.DataFrame()

    if not filt_awards.empty and sel_methods:
        filt_awards = filt_awards[filt_awards["procurement_method"].isin(sel_methods)]
    if buyer_query:
        q = buyer_query.lower()
        if not filt_awards.empty:
            filt_awards = filt_awards[filt_awards["procuring_entity"].str.lower().str.contains(q, na=False)]
        if not filt_bids.empty:
            filt_bids = filt_bids[filt_bids["procuring_entity"].str.lower().str.contains(q, na=False)]
    if kw_query:
        q = kw_query.lower()
        if not filt_awards.empty:
            filt_awards = filt_awards[filt_awards["title"].str.lower().str.contains(q, na=False)]
        if not filt_bids.empty:
            filt_bids = filt_bids[filt_bids["cft_title"].str.lower().str.contains(q, na=False)]

    # ─── TABS ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview", "📋 Awards", "🏛️ Buyers",
        "📈 Benchmarks", "📅 Seasonality", "🔓 Open Bids"
    ])

    # ── TAB 1: Overview KPIs ──────────────────────────────────────────────────
    with tab1:
        st.markdown("## Key Performance Indicators")
        k1, k2, k3, k4, k5 = st.columns(5)
        total_awards = len(filt_awards)
        total_value = filt_awards["contract_amount_jmd"].sum() if not filt_awards.empty else 0
        avg_value = filt_awards["contract_amount_jmd"].mean() if not filt_awards.empty else 0
        unique_buyers = filt_awards["procuring_entity"].nunique() if not filt_awards.empty else 0
        total_bids = len(filt_bids)
        with k1: st.metric("Contract Awards", f"{total_awards:,}")
        with k2: st.metric("Total Value (JMD)", fmt_jmd(total_value))
        with k3: st.metric("Avg Award Value", fmt_jmd(avg_value))
        with k4: st.metric("Unique Buyers", f"{unique_buyers:,}")
        with k5: st.metric("Opened Bids", f"{total_bids:,}")

        st.markdown("---")
        if not filt_awards.empty and "year_month" in filt_awards.columns:
            st.markdown("### Awards by Month")
            monthly = (
                filt_awards.groupby("year_month")
                .agg(count=("title", "count"), total_value=("contract_amount_jmd", "sum"))
                .reset_index().sort_values("year_month")
            )
            col_l, col_r = st.columns(2)
            with col_l:
                fig = px.bar(monthly, x="year_month", y="count", title="Awards Count per Month",
                             color_discrete_sequence=[GREEN])
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                fig2 = px.line(monthly, x="year_month", y="total_value", title="Total Value per Month (JMD)",
                               markers=True, color_discrete_sequence=[GOLD])
                fig2.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig2, use_container_width=True)

        if not filt_awards.empty:
            st.markdown("### Procurement Method Breakdown")
            col_l, col_r = st.columns(2)
            method_cnt = filt_awards["procurement_method"].value_counts().reset_index()
            method_cnt.columns = ["Method", "Count"]
            method_val = filt_awards.groupby("procurement_method")["contract_amount_jmd"].sum().reset_index()
            method_val.columns = ["Method", "Total Value (JMD)"]
            with col_l:
                fig = px.pie(method_cnt, names="Method", values="Count", title="By Count",
                             color_discrete_sequence=px.colors.qualitative.Safe)
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                fig2 = px.pie(method_val, names="Method", values="Total Value (JMD)", title="By Value",
                              color_discrete_sequence=px.colors.qualitative.Safe)
                st.plotly_chart(fig2, use_container_width=True)

    # ── TAB 2: Awards Table ───────────────────────────────────────────────────
    with tab2:
        st.markdown("## Contract Award Notices")
        if not filt_awards.empty:
            show_cols = [c for c in ["procurement_method","procuring_entity","title","contract_amount_jmd","publication_date","category","notice_pdf_url"] if c in filt_awards.columns]
            show_df = filt_awards[show_cols].copy()
            show_df = show_df.rename(columns={
                "procurement_method":"Method","procuring_entity":"Buyer","title":"Title",
                "contract_amount_jmd":"Amount (JMD)","publication_date":"Date",
                "category":"Category","notice_pdf_url":"PDF"
            })
            if "Amount (JMD)" in show_df.columns:
                show_df["Amount (JMD)"] = show_df["Amount (JMD)"].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "")
            st.dataframe(show_df, use_container_width=True, height=450)
            csv_download_btn(filt_awards, "Awards", "jamaica_awards_filtered.csv")

            st.markdown("### Price Bands" + (f" — keyword: *{kw_query}*" if kw_query else ""))
            band_df = filt_awards.dropna(subset=["contract_amount_jmd"]).copy()
            bins = [0, 500_000, 2_000_000, 5_000_000, 10_000_000, 50_000_000, float("inf")]
            labels = ["<500K","500K-2M","2M-5M","5M-10M","10M-50M",">50M"]
            band_df["price_band"] = pd.cut(band_df["contract_amount_jmd"], bins=bins, labels=labels)
            band_counts = band_df["price_band"].value_counts().sort_index().reset_index()
            band_counts.columns = ["Price Band (JMD)", "Count"]
            fig = px.bar(band_counts, x="Price Band (JMD)", y="Count",
                         title="Contract Value Distribution", color_discrete_sequence=[GREEN])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No awards data matches your filters.")

    # ── TAB 3: Buyer Intelligence ─────────────────────────────────────────────
    with tab3:
        st.markdown("## Top Procuring Entities")
        if not filt_awards.empty:
            col_l, col_r = st.columns(2)
            top_val = filt_awards.groupby("procuring_entity")["contract_amount_jmd"].sum().nlargest(15).reset_index()
            top_val.columns = ["Procuring Entity","Total Value (JMD)"]
            top_cnt = filt_awards.groupby("procuring_entity").size().nlargest(15).reset_index(name="Count")
            with col_l:
                fig = px.bar(top_val, x="Total Value (JMD)", y="Procuring Entity", orientation="h",
                             title="Top 15 by Total Value", color_discrete_sequence=[GREEN])
                fig.update_layout(yaxis={"categoryorder":"total ascending"})
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                fig2 = px.bar(top_cnt, x="Count", y="procuring_entity", orientation="h",
                              title="Top 15 by Award Count", color_discrete_sequence=[GOLD])
                fig2.update_layout(yaxis={"categoryorder":"total ascending"})
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("### Supplier Intelligence Summary")
            supplier_df = (
                filt_awards.groupby("procuring_entity")
                .agg(
                    award_count=("title","count"),
                    total_value=("contract_amount_jmd","sum"),
                    avg_value=("contract_amount_jmd","mean"),
                    categories=("category", lambda x: ", ".join(sorted(set(x.dropna()))))
                ).reset_index()
                .sort_values("total_value", ascending=False)
                .rename(columns={
                    "procuring_entity":"Buyer","award_count":"Awards",
                    "total_value":"Total Value (JMD)","avg_value":"Avg Value (JMD)","categories":"Categories"
                })
            )
            supplier_df["Total Value (JMD)"] = supplier_df["Total Value (JMD)"].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
            supplier_df["Avg Value (JMD)"] = supplier_df["Avg Value (JMD)"].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
            st.dataframe(supplier_df, use_container_width=True, height=400)
            csv_download_btn(supplier_df, "Buyers", "jamaica_buyers.csv")
        else:
            st.info("No data matches your filters.")

    # ── TAB 4: Price Benchmarks ───────────────────────────────────────────────
    with tab4:
        st.markdown("## Price Benchmark Module")
        st.markdown("Compare contract values across buyers and categories.")
        if not filt_awards.empty:
            col_l, col_r = st.columns(2)
            with col_l:
                bench_buyer = st.selectbox("Select buyer", ["All"] + sorted(filt_awards["procuring_entity"].dropna().unique().tolist()))
            with col_r:
                if "category" in filt_awards.columns:
                    bench_cat = st.selectbox("Select category", ["All"] + sorted(filt_awards["category"].dropna().unique().tolist()))
                else:
                    bench_cat = "All"

            bench_df = filt_awards.dropna(subset=["contract_amount_jmd"]).copy()
            if bench_buyer != "All":
                bench_df = bench_df[bench_df["procuring_entity"] == bench_buyer]
            if bench_cat != "All":
                bench_df = bench_df[bench_df["category"] == bench_cat]

            if not bench_df.empty:
                m1, m2, m3, m4, m5 = st.columns(5)
                with m1: st.metric("Count", f"{len(bench_df):,}")
                with m2: st.metric("Min", fmt_jmd(bench_df["contract_amount_jmd"].min()))
                with m3: st.metric("Max", fmt_jmd(bench_df["contract_amount_jmd"].max()))
                with m4: st.metric("Median", fmt_jmd(bench_df["contract_amount_jmd"].median()))
                with m5: st.metric("Average", fmt_jmd(bench_df["contract_amount_jmd"].mean()))

                fig = px.histogram(bench_df, x="contract_amount_jmd", nbins=20,
                                   title="Value Distribution", color_discrete_sequence=[GREEN])
                fig.update_xaxes(title="Contract Amount (JMD)")
                st.plotly_chart(fig, use_container_width=True)

                if bench_buyer == "All" and bench_cat != "All":
                    top_buyers_bench = bench_df.groupby("procuring_entity")["contract_amount_jmd"].median().nlargest(10).reset_index()
                    top_buyers_bench.columns = ["Buyer","Median Value (JMD)"]
                    fig2 = px.bar(top_buyers_bench, x="Median Value (JMD)", y="Buyer", orientation="h",
                                  title=f"Median Contract Value by Buyer - {bench_cat}",
                                  color_discrete_sequence=[GOLD])
                    fig2.update_layout(yaxis={"categoryorder":"total ascending"})
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("No data for selected filters.")
        else:
            st.info("No awards data available.")

    # ── TAB 5: Buyer Seasonality ──────────────────────────────────────────────
    with tab5:
        st.markdown("## Buyer Seasonality Module")
        st.markdown("Monthly purchasing patterns by procuring entity.")
        if not filt_awards.empty and "year_month" in filt_awards.columns:
            all_buyers = sorted(filt_awards["procuring_entity"].dropna().unique().tolist())
            selected_buyers = st.multiselect(
                "Select buyers to compare (max 5):",
                all_buyers,
                default=all_buyers[:min(3, len(all_buyers))]
            )
            if selected_buyers:
                season_df = filt_awards[filt_awards["procuring_entity"].isin(selected_buyers)]
                season_monthly = (
                    season_df.groupby(["procuring_entity","year_month"])
                    .agg(count=("title","count"), total_value=("contract_amount_jmd","sum"))
                    .reset_index()
                    .sort_values("year_month")
                )
                col_l, col_r = st.columns(2)
                with col_l:
                    fig = px.line(season_monthly, x="year_month", y="count", color="procuring_entity",
                                  markers=True, title="Monthly Award Frequency by Buyer",
                                  labels={"count":"Awards","year_month":"Month","procuring_entity":"Buyer"})
                    fig.update_layout(xaxis_tickangle=-45, legend=dict(orientation="h", yanchor="bottom", y=-0.4))
                    st.plotly_chart(fig, use_container_width=True)
                with col_r:
                    fig2 = px.line(season_monthly, x="year_month", y="total_value", color="procuring_entity",
                                   markers=True, title="Monthly Award Value by Buyer (JMD)",
                                   labels={"total_value":"Value (JMD)","year_month":"Month","procuring_entity":"Buyer"})
                    fig2.update_layout(xaxis_tickangle=-45, legend=dict(orientation="h", yanchor="bottom", y=-0.4))
                    st.plotly_chart(fig2, use_container_width=True)

                st.markdown("### Heatmap — Award Count by Buyer & Month")
                pivot = season_monthly.pivot(index="procuring_entity", columns="year_month", values="count").fillna(0)
                fig3 = px.imshow(pivot, aspect="auto", color_continuous_scale="YlOrRd",
                                 title="Award Frequency Heatmap", labels=dict(color="Awards"))
                fig3.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("Select at least one buyer above.")
        else:
            st.info("No awards data with date information available.")

    # ── TAB 6: Open Bids ─────────────────────────────────────────────────────
    with tab6:
        st.markdown("## Recent Open Bid Opportunities")
        if not filt_bids.empty:
            k1, k2, k3 = st.columns(3)
            with k1: st.metric("Total Open Bids", f"{len(filt_bids):,}")
            with k2:
                active = filt_bids[filt_bids["status"].str.lower().str.contains("open|evaluation", na=False)]
                st.metric("Active / Evaluation", f"{len(active):,}")
            with k3:
                upcoming = filt_bids[filt_bids["submission_deadline"] > pd.Timestamp.now()] if "submission_deadline" in filt_bids.columns else pd.DataFrame()
                st.metric("Upcoming Deadlines", f"{len(upcoming):,}")

            show_cols_b = [c for c in ["cft_title","reference_number","procuring_entity","submission_deadline","procurement_method","status","category","opened_bids_url"] if c in filt_bids.columns]
            show_bids = filt_bids[show_cols_b].rename(columns={
                "cft_title":"Title","reference_number":"Ref #","procuring_entity":"Buyer",
                "submission_deadline":"Deadline","procurement_method":"Method",
                "status":"Status","category":"Category","opened_bids_url":"Bids URL"
            })
            st.dataframe(show_bids, use_container_width=True, height=450)
            csv_download_btn(filt_bids, "Open Bids", "jamaica_bids_filtered.csv")

            if "category" in filt_bids.columns:
                cat_counts = filt_bids["category"].value_counts().reset_index()
                cat_counts.columns = ["Category","Count"]
                fig = px.bar(cat_counts, x="Category", y="Count", title="Open Bids by Category",
                             color_discrete_sequence=[GREEN])
                fig.update_layout(xaxis_tickangle=-30)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No opened bids data matches your filters.")


if __name__ == "__main__":
    main()
