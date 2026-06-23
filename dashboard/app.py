"""
Jamaica Procurement OS — Dashboard v2
Tabs: Overview | Category Intel | Supplier Intel | Benchmark | Seasonality | Competition | Insights | Watchlist | Opportunities | Audit
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from utils.helpers import classify_category, fmt_jmd, CATEGORY_COLORS, CATEGORY_LIST, clean_amount, clean_date
from utils.insights_engine import generate_insights

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Jamaica Procurement OS",
    page_icon="JA",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""<style>
[data-testid="stMetricValue"]{font-size:1.6rem;font-weight:700;}
.insight-card{background:#1E1E2E;border-left:4px solid #F39C12;padding:12px 16px;border-radius:6px;margin:6px 0;}
.insight-high{border-left-color:#E74C3C;}
.insight-medium{border-left-color:#F39C12;}
.insight-low{border-left-color:#3498DB;}
</style>""", unsafe_allow_html=True)

# ── Data Loading ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    """Load from DB or fall back to sample CSVs."""
    awards, bids = pd.DataFrame(), pd.DataFrame()
    try:
        from database.db import get_engine, init_db
        init_db()
        engine = get_engine()
        awards = pd.read_sql("SELECT * FROM contract_awards", engine)
        bids   = pd.read_sql("SELECT * FROM opened_bids", engine)
    except Exception:
        pass
    # Fall back to sample CSVs if DB empty
    base = os.path.join(os.path.dirname(__file__), "..", "data")
    if awards.empty:
        try: awards = pd.read_csv(os.path.join(base, "sample_awards.csv"))
        except: pass
    if bids.empty:
        try: bids = pd.read_csv(os.path.join(base, "sample_bids.csv"))
        except: pass
    # --- Clean amounts and dates ---
    for col in ["contract_amount_jmd"]:
        if col in awards.columns:
            awards[col] = awards[col].apply(clean_amount)
    for col in ["publication_date"]:
        if col in awards.columns:
            awards[col] = awards[col].apply(clean_date)
    for col in ["submission_deadline","award_date"]:
        if col in bids.columns:
            bids[col] = bids[col].apply(clean_date)
    # --- Apply category if missing ---
    if "normalized_category" not in awards.columns or awards["normalized_category"].isna().all():
        awards[["normalized_category","category_confidence"]] = awards.get("title", pd.Series([""] * len(awards))).apply(
            lambda t: pd.Series(classify_category(t))
        )
    if "normalized_category" not in bids.columns or bids["normalized_category"].isna().all():
        bids[["normalized_category","category_confidence"]] = bids.get("cft_title", pd.Series([""] * len(bids))).apply(
            lambda t: pd.Series(classify_category(t))
        )
    return awards, bids

@st.cache_data(ttl=300)
def load_watchlist():
    try:
        from database.db import get_engine
        return pd.read_sql("SELECT * FROM watchlists", get_engine())
    except:
        return pd.DataFrame(columns=["id","watch_type","watch_value","created_at"])

awards_df, bids_df = load_data()

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/4/43/Flag_of_Jamaica.svg", width=80)
    st.title("Jamaica Procurement OS")
    st.caption("Private Beta — Not for public distribution")
    st.markdown("---")
    st.metric("Awards Tracked", "{:,}".format(len(awards_df)))
    st.metric("Bids Tracked", "{:,}".format(len(bids_df)))
    if "contract_amount_jmd" in awards_df.columns:
        total_val = pd.to_numeric(awards_df["contract_amount_jmd"], errors="coerce").sum()
        st.metric("Total Value", fmt_jmd(total_val))
    st.markdown("---")
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Tabs ─────────────────────────────────────────────────────
tabs = st.tabs([
    "Overview", "Category Intel", "Supplier Intel",
    "Benchmark", "Seasonality", "Competition",
    "Insights", "Watchlist", "Opportunities", "Audit"
])

# ════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════
with tabs[0]:
    st.header("Overview")
    df = awards_df.copy()
    if df.empty:
        st.warning("No award data. Run the scraper or upload sample data.")
    else:
        df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd", 0), errors="coerce").fillna(0)
        total = df["contract_amount_jmd"].sum()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Awards", "{:,}".format(len(df)))
        c2.metric("Total Value (JMD)", fmt_jmd(total))
        c3.metric("Unique Buyers", df["procuring_entity"].nunique() if "procuring_entity" in df.columns else 0)
        c4.metric("Open Bids", len(bids_df))

        # Awards by month
        if "publication_date" in df.columns:
            df["pub_dt"] = pd.to_datetime(df["publication_date"], errors="coerce")
            monthly = df.dropna(subset=["pub_dt"]).groupby(df["pub_dt"].dt.to_period("M").astype(str)).agg(
                count=("id","count"), value=("contract_amount_jmd","sum")).reset_index()
            monthly.columns = ["Month","Count","Value"]
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Awards by Month (Count)")
                fig = px.bar(monthly, x="Month", y="Count", color_discrete_sequence=["#F39C12"])
                fig.update_layout(height=300, margin=dict(t=20,b=40))
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.subheader("Award Value by Month (JMD)")
                fig2 = px.bar(monthly, x="Month", y="Value", color_discrete_sequence=["#2ECC71"])
                fig2.update_layout(height=300, margin=dict(t=20,b=40))
                st.plotly_chart(fig2, use_container_width=True)

        # Top buyers
        if "procuring_entity" in df.columns:
            col3, col4 = st.columns(2)
            top_val = df.groupby("procuring_entity")["contract_amount_jmd"].sum().nlargest(10).reset_index()
            top_val.columns = ["Buyer","Total Value"]
            with col3:
                st.subheader("Top 10 Buyers by Value")
                fig3 = px.bar(top_val, x="Total Value", y="Buyer", orientation="h", color_discrete_sequence=["#9B59B6"])
                fig3.update_layout(height=350, margin=dict(t=20,b=20))
                st.plotly_chart(fig3, use_container_width=True)
            top_cnt = df.groupby("procuring_entity").size().nlargest(10).reset_index()
            top_cnt.columns = ["Buyer","Count"]
            with col4:
                st.subheader("Top 10 Buyers by Count")
                fig4 = px.bar(top_cnt, x="Count", y="Buyer", orientation="h", color_discrete_sequence=["#E74C3C"])
                fig4.update_layout(height=350, margin=dict(t=20,b=20))
                st.plotly_chart(fig4, use_container_width=True)

        # Procurement method breakdown
        if "procurement_method" in df.columns:
            pm = df["procurement_method"].value_counts().reset_index()
            pm.columns = ["Method","Count"]
            col5, col6 = st.columns(2)
            with col5:
                st.subheader("Procurement Method Breakdown")
                fig5 = px.pie(pm, values="Count", names="Method")
                fig5.update_layout(height=300)
                st.plotly_chart(fig5, use_container_width=True)

        # Search + export
        st.subheader("Search & Export")
        col7, col8 = st.columns([3,1])
        search_kw = col7.text_input("Search by keyword, buyer, or title", key="overview_search")
        buyer_list = ["All"] + sorted(df.get("procuring_entity", pd.Series()).dropna().unique().tolist())
        sel_buyer = col8.selectbox("Filter by buyer", buyer_list, key="overview_buyer")
        fdf = df.copy()
        if search_kw:
            mask = fdf.apply(lambda r: search_kw.lower() in str(r).lower(), axis=1)
            fdf = fdf[mask]
        if sel_buyer != "All":
            fdf = fdf[fdf["procuring_entity"] == sel_buyer]
        st.dataframe(fdf.head(200), use_container_width=True)
        st.download_button("Export CSV", fdf.to_csv(index=False), "awards_export.csv", "text/csv")
# ════════════════════════════════════════════════════════════
# TAB 2 — CATEGORY INTELLIGENCE
# ════════════════════════════════════════════════════════════
with tabs[1]:
    st.header("Category Intelligence Engine")
    df = awards_df.copy()
    if df.empty:
        st.warning("No data loaded.")
    else:
        df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd",0), errors="coerce").fillna(0)
        if "normalized_category" not in df.columns:
            df[["normalized_category","category_confidence"]] = df.get("title",pd.Series([""]*len(df))).apply(lambda t: pd.Series(classify_category(t)))

        cat_val = df.groupby("normalized_category")["contract_amount_jmd"].sum().sort_values(ascending=False).reset_index()
        cat_cnt = df.groupby("normalized_category").size().reset_index(name="count")
        cat_merged = cat_val.merge(cat_cnt, on="normalized_category")
        cat_merged.columns = ["Category","Total Value","Count"]

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Award Value by Category")
            fig = px.bar(cat_merged.head(15), x="Total Value", y="Category", orientation="h",
                color="Category", color_discrete_map=CATEGORY_COLORS)
            fig.update_layout(height=400, showlegend=False, margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Category Frequency")
            fig2 = px.pie(cat_merged.head(12), values="Count", names="Category",
                color="Category", color_discrete_map=CATEGORY_COLORS)
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)

        # Category value concentration (Pareto)
        st.subheader("Value Concentration (Pareto)")
        cat_sorted = cat_merged.sort_values("Total Value", ascending=False).copy()
        cat_sorted["Cumulative %"] = (cat_sorted["Total Value"].cumsum() / cat_sorted["Total Value"].sum() * 100).round(1)
        fig3 = go.Figure()
        fig3.add_bar(x=cat_sorted["Category"], y=cat_sorted["Total Value"], name="Value", marker_color="#F39C12")
        fig3.add_scatter(x=cat_sorted["Category"], y=cat_sorted["Cumulative %"], name="Cumulative %", yaxis="y2", line=dict(color="#E74C3C"))
        fig3.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0,105], title="Cumulative %"),
            height=350, margin=dict(t=20,b=60))
        st.plotly_chart(fig3, use_container_width=True)

        # Category growth over time
        if "publication_date" in df.columns:
            st.subheader("Category Growth Over Time")
            df["pub_dt"] = pd.to_datetime(df["publication_date"], errors="coerce")
            sel_cats = st.multiselect("Select categories", CATEGORY_LIST, default=CATEGORY_LIST[:5], key="cat_growth_sel")
            if sel_cats:
                cgdf = df[df["normalized_category"].isin(sel_cats)].dropna(subset=["pub_dt"])
                cgdf["Month"] = cgdf["pub_dt"].dt.to_period("M").astype(str)
                cg = cgdf.groupby(["Month","normalized_category"]).size().reset_index(name="count")
                fig4 = px.line(cg, x="Month", y="count", color="normalized_category",
                    color_discrete_map=CATEGORY_COLORS, markers=True)
                fig4.update_layout(height=350, margin=dict(t=10,b=40))
                st.plotly_chart(fig4, use_container_width=True)

        st.subheader("Category Summary Table")
        st.dataframe(cat_merged, use_container_width=True)

# ════════════════════════════════════════════════════════════
# TAB 3 — SUPPLIER INTELLIGENCE
# ════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("Supplier Intelligence")
    st.caption("Supplier data extracted where available from award notices.")
    df = awards_df.copy()
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd",0), errors="coerce").fillna(0)
    # Try loading from suppliers table first
    sup_df = pd.DataFrame()
    try:
        from database.db import get_engine
        sup_df = pd.read_sql("SELECT * FROM suppliers", get_engine())
    except: pass

    # Fall back to deriving from awards
    if sup_df.empty and "supplier_name" in df.columns:
        sdf = df[df["supplier_name"].notna() & (df["supplier_name"] != "")].copy()
        if not sdf.empty:
            sup_df = sdf.groupby("supplier_name").agg(
                award_count=("id","count"),
                total_award_value=("contract_amount_jmd","sum"),
                avg_award_value=("contract_amount_jmd","mean"),
            ).reset_index()

    if sup_df.empty:
        st.info("No supplier data yet. Supplier names will be extracted as scraper runs and bid-opening PDFs are parsed.")
    else:
        sup_df["total_award_value"] = pd.to_numeric(sup_df.get("total_award_value",0), errors="coerce").fillna(0)
        sup_df["award_count"] = pd.to_numeric(sup_df.get("award_count",0), errors="coerce").fillna(0)
        sup_df["avg_award_value"] = pd.to_numeric(sup_df.get("avg_award_value",0), errors="coerce").fillna(0)

        c1, c2, c3 = st.columns(3)
        c1.metric("Unique Suppliers", "{:,}".format(len(sup_df)))
        c2.metric("Total Supplier Awards", "{:,}".format(int(sup_df["award_count"].sum())))
        c3.metric("Avg Contract Size", fmt_jmd(sup_df["avg_award_value"].mean()))

        # Leaderboard
        st.subheader("Top Suppliers by Value")
        top_sup = sup_df.nlargest(15,"total_award_value")
        fig = px.bar(top_sup, x="total_award_value", y="supplier_name", orientation="h", color_discrete_sequence=["#9B59B6"])
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Search supplier
        st.subheader("Supplier Lookup")
        sup_search = st.text_input("Search supplier name", key="sup_search")
        if sup_search:
            res = sup_df[sup_df["supplier_name"].str.contains(sup_search, case=False, na=False)]
            if res.empty:
                st.warning("No supplier found matching: " + sup_search)
            else:
                for _, row in res.head(5).iterrows():
                    with st.expander(row["supplier_name"]):
                        st.write("**Total Wins:** {:,}".format(int(row["award_count"])))
                        st.write("**Total Value:** " + fmt_jmd(row["total_award_value"]))
                        st.write("**Avg Contract:** " + fmt_jmd(row["avg_award_value"]))
        st.subheader("Full Supplier Register")
        st.dataframe(sup_df.sort_values("total_award_value", ascending=False), use_container_width=True)
        st.download_button("Export Supplier Data", sup_df.to_csv(index=False), "suppliers.csv", "text/csv")
# ════════════════════════════════════════════════════════════
# TAB 4 — PRICE BENCHMARK ENGINE
# ════════════════════════════════════════════════════════════
with tabs[3]:
    st.header("Price Benchmark Engine")
    st.caption("Answer: What does a typical [category] contract at [buyer] cost?")
    df = awards_df.copy()
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd",0), errors="coerce")
    df = df[df["contract_amount_jmd"] > 0]

    if df.empty:
        st.warning("No valid contract amount data available.")
    else:
        col1, col2 = st.columns(2)
        all_buyers = ["All Buyers"] + sorted(df.get("procuring_entity",pd.Series()).dropna().unique().tolist())
        all_cats   = ["All Categories"] + CATEGORY_LIST
        sel_bm_buyer = col1.selectbox("Select Buyer", all_buyers, key="bm_buyer")
        sel_bm_cat   = col2.selectbox("Select Category", all_cats, key="bm_cat")

        bm = df.copy()
        if sel_bm_buyer != "All Buyers":
            bm = bm[bm["procuring_entity"] == sel_bm_buyer]
        if sel_bm_cat != "All Categories":
            if "normalized_category" in bm.columns:
                bm = bm[bm["normalized_category"] == sel_bm_cat]

        if bm.empty:
            st.info("No contracts match this buyer/category combination.")
        else:
            amounts = bm["contract_amount_jmd"].dropna()
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Min", fmt_jmd(amounts.min()))
            c2.metric("Max", fmt_jmd(amounts.max()))
            c3.metric("Median", fmt_jmd(amounts.median()))
            c4.metric("Average", fmt_jmd(amounts.mean()))
            c5.metric("Std Dev", fmt_jmd(amounts.std()))
            st.metric("Contracts Analysed", "{:,}".format(len(amounts)))

            # Distribution chart
            st.subheader("Price Distribution")
            fig = px.histogram(bm, x="contract_amount_jmd", nbins=30, color_discrete_sequence=["#F39C12"])
            fig.update_layout(height=300, xaxis_title="Contract Amount (JMD)", margin=dict(t=10))
            st.plotly_chart(fig, use_container_width=True)

            # Price trend over time
            if "publication_date" in bm.columns:
                st.subheader("Price Trend Over Time")
                bm["pub_dt"] = pd.to_datetime(bm["publication_date"], errors="coerce")
                trend = bm.dropna(subset=["pub_dt"]).copy()
                trend["Month"] = trend["pub_dt"].dt.to_period("M").astype(str)
                trend_agg = trend.groupby("Month")["contract_amount_jmd"].median().reset_index()
                trend_agg.columns = ["Month","Median Amount"]
                fig2 = px.line(trend_agg, x="Month", y="Median Amount", markers=True, color_discrete_sequence=["#2ECC71"])
                fig2.update_layout(height=280, margin=dict(t=10,b=40))
                st.plotly_chart(fig2, use_container_width=True)

            # Price bands
            st.subheader("Price Band Distribution")
            bins = [0, 1e6, 5e6, 20e6, 100e6, 500e6, 1e13]
            labels = ["<1M","1-5M","5-20M","20-100M","100-500M",">500M"]
            bm["band"] = pd.cut(bm["contract_amount_jmd"], bins=bins, labels=labels)
            band_cnt = bm["band"].value_counts().sort_index().reset_index()
            band_cnt.columns = ["Band","Count"]
            fig3 = px.bar(band_cnt, x="Band", y="Count", color_discrete_sequence=["#9B59B6"])
            fig3.update_layout(height=280)
            st.plotly_chart(fig3, use_container_width=True)

            # Underlying data
            with st.expander("View matching contracts"):
                show_cols = [c for c in ["procuring_entity","title","contract_amount_jmd","publication_date","normalized_category"] if c in bm.columns]
                st.dataframe(bm[show_cols].head(100), use_container_width=True)

# ════════════════════════════════════════════════════════════
# TAB 5 — BUYER SEASONALITY ENGINE
# ════════════════════════════════════════════════════════════
with tabs[4]:
    st.header("Buyer Seasonality Engine")
    st.caption("Predict procurement behaviour. When does each buyer spend?")
    df = awards_df.copy()
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd",0), errors="coerce").fillna(0)

    if df.empty or "procuring_entity" not in df.columns:
        st.warning("No data.")
    else:
        buyers = sorted(df["procuring_entity"].dropna().unique().tolist())
        sel_sea_buyer = st.selectbox("Select Buyer to Analyse", buyers, key="sea_buyer")
        sdf = df[df["procuring_entity"] == sel_sea_buyer].copy()

        if "publication_date" in sdf.columns:
            sdf["pub_dt"] = pd.to_datetime(sdf["publication_date"], errors="coerce")
            sdf = sdf.dropna(subset=["pub_dt"])
            sdf["Month"]   = sdf["pub_dt"].dt.month
            sdf["MonthName"] = sdf["pub_dt"].dt.strftime("%b")
            sdf["Quarter"] = sdf["pub_dt"].dt.to_period("Q").astype(str)
            sdf["Year"]    = sdf["pub_dt"].dt.year

            c1, c2 = st.columns(2)
            c1.metric("Total Contracts", "{:,}".format(len(sdf)))
            c2.metric("Total Spend", fmt_jmd(sdf["contract_amount_jmd"].sum()))

            # Monthly count heatmap
            monthly_cnt = sdf.groupby(["Year","Month"]).size().reset_index(name="count")
            monthly_cnt["MonthName"] = monthly_cnt["Month"].apply(lambda m: datetime(2000,m,1).strftime("%b"))
            st.subheader("Monthly Award Frequency")
            fig = px.density_heatmap(monthly_cnt, x="MonthName", y="Year", z="count", color_continuous_scale="YlOrRd")
            fig.update_layout(height=320, margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True)

            # Monthly value
            monthly_val = sdf.groupby("MonthName")["contract_amount_jmd"].sum().reset_index()
            monthly_val.columns = ["Month","Total Value"]
            month_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            monthly_val["Month"] = pd.Categorical(monthly_val["Month"], categories=month_order, ordered=True)
            monthly_val = monthly_val.sort_values("Month")
            st.subheader("Monthly Spend Pattern")
            fig2 = px.bar(monthly_val, x="Month", y="Total Value", color_discrete_sequence=["#3498DB"])
            fig2.update_layout(height=280)
            st.plotly_chart(fig2, use_container_width=True)

            # Quarterly trend
            qtrend = sdf.groupby("Quarter").agg(count=("id","count"),value=("contract_amount_jmd","sum")).reset_index()
            st.subheader("Quarterly Trend")
            fig3 = px.bar(qtrend, x="Quarter", y="count", color_discrete_sequence=["#F39C12"])
            fig3.update_layout(height=260)
            st.plotly_chart(fig3, use_container_width=True)

            # Category concentration for this buyer
            if "normalized_category" in sdf.columns:
                st.subheader("Category Concentration for " + sel_sea_buyer[:60])
                cat_conc = sdf.groupby("normalized_category")["contract_amount_jmd"].sum().sort_values(ascending=False).reset_index()
                fig4 = px.pie(cat_conc, values="contract_amount_jmd", names="normalized_category",
                    color="normalized_category", color_discrete_map=CATEGORY_COLORS)
                fig4.update_layout(height=320)
                st.plotly_chart(fig4, use_container_width=True)
# ════════════════════════════════════════════════════════════
# TAB 6 — COMPETITION DENSITY ENGINE
# ════════════════════════════════════════════════════════════
with tabs[5]:
    st.header("Competition Density Engine")
    st.caption("Understand how competitive each sector is. Find low-competition entry points.")
    df = awards_df.copy()
    if df.empty:
        st.warning("No data.")
    else:
        # Try DB competition_metrics table
        comp_df = pd.DataFrame()
        try:
            from database.db import get_engine
            comp_df = pd.read_sql("SELECT * FROM competition_metrics", get_engine())
        except: pass

        # Derive from bids bidder_count if available
        if comp_df.empty and not bids_df.empty and "bidder_count" in bids_df.columns:
            bdf = bids_df.copy()
            bdf["bidder_count"] = pd.to_numeric(bdf["bidder_count"], errors="coerce")
            bdf = bdf[bdf["bidder_count"] > 0]
            if not bdf.empty:
                comp_df = bdf.groupby("normalized_category")["bidder_count"].agg(
                    avg_bidders="mean", median_bidders="median",
                    min_bidders="min", max_bidders="max", total_tenders="count"
                ).reset_index()

        if not comp_df.empty and "avg_bidders" in comp_df.columns:
            comp_df["avg_bidders"] = pd.to_numeric(comp_df["avg_bidders"], errors="coerce")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Average Bidders by Category")
                fig = px.bar(comp_df.sort_values("avg_bidders", ascending=False),
                    x="avg_bidders", y="normalized_category" if "normalized_category" in comp_df.columns else "category",
                    orientation="h", color_discrete_sequence=["#E07B39"])
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("Low vs High Competition Sectors")
                cat_col = "normalized_category" if "normalized_category" in comp_df.columns else "category"
                low = comp_df[comp_df["avg_bidders"] <= 3].sort_values("avg_bidders")
                high = comp_df[comp_df["avg_bidders"] > 5].sort_values("avg_bidders", ascending=False)
                st.markdown("**Low Competition (avg ≤ 3 bidders)**")
                if not low.empty:
                    st.dataframe(low[[cat_col,"avg_bidders","total_tenders"]].head(10), use_container_width=True)
                else:
                    st.info("No low-competition data yet.")
                st.markdown("**High Competition (avg > 5 bidders)**")
                if not high.empty:
                    st.dataframe(high[[cat_col,"avg_bidders","total_tenders"]].head(10), use_container_width=True)
                else:
                    st.info("No high-competition data yet.")
        else:
            st.info("Competition data will populate as scraped bid openings include bidder counts. Currently building baseline...")
            # Show procurement method as proxy for competition
            if "procurement_method" in df.columns:
                st.subheader("Procurement Method (Competition Proxy)")
                pm = df["procurement_method"].value_counts().reset_index()
                pm.columns = ["Method","Count"]
                fig = px.bar(pm, x="Count", y="Method", orientation="h", color_discrete_sequence=["#16A085"])
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════
# TAB 7 — INSIGHTS ENGINE
# ════════════════════════════════════════════════════════════
with tabs[6]:
    st.header("Auto-Generated Intelligence Insights")
    insights = generate_insights(awards_df, bids_df)
    if not insights:
        st.info("No insights generated yet.")
    else:
        for ins in insights:
            sev = ins.get("severity","medium")
            css_class = "insight-" + sev
            icon = ins.get("icon","I")
            headline = ins.get("headline","")
            detail = ins.get("detail","")
            st.markdown(
                "<div class='insight-card {css}'><strong>[{icon}]</strong> {h}<br><small>{d}</small></div>".format(
                    css=css_class, icon=icon, h=headline, d=detail),
                unsafe_allow_html=True
            )

# ════════════════════════════════════════════════════════════
# TAB 8 — WATCHLIST
# ════════════════════════════════════════════════════════════
with tabs[7]:
    st.header("Watchlist")
    st.caption("Track buyers, suppliers, and categories you care about.")
    w1, w2 = st.columns([2,1])
    watch_type_opts = ["buyer","supplier","category"]
    sel_wtype = w1.selectbox("Watch type", watch_type_opts, key="wl_type")
    sel_wval  = w2.text_input("Value to watch", key="wl_val")
    if st.button("Add to Watchlist", key="wl_add"):
        if sel_wval.strip():
            try:
                from database.db import get_engine, add_watchlist
                with get_engine().begin() as conn:
                    add_watchlist(conn, sel_wtype, sel_wval.strip())
                st.success("Added: {} — {}".format(sel_wtype, sel_wval))
                st.cache_data.clear()
            except Exception as e:
                st.error("Could not save: " + str(e))
        else:
            st.warning("Enter a value to watch.")

    wl_df = load_watchlist()
    if wl_df.empty:
        st.info("Your watchlist is empty. Add buyers, suppliers, or categories above.")
    else:
        st.subheader("Your Watchlist")
        for _, row in wl_df.iterrows():
            with st.expander("{} — {}".format(row["watch_type"].upper(), row["watch_value"])):
                # Show recent activity for this item
                df_w = awards_df.copy()
                if row["watch_type"] == "buyer" and "procuring_entity" in df_w.columns:
                    hits = df_w[df_w["procuring_entity"].str.contains(row["watch_value"], case=False, na=False)]
                elif row["watch_type"] == "category" and "normalized_category" in df_w.columns:
                    hits = df_w[df_w["normalized_category"] == row["watch_value"]]
                elif row["watch_type"] == "supplier" and "supplier_name" in df_w.columns:
                    hits = df_w[df_w["supplier_name"].str.contains(row["watch_value"], case=False, na=False)]
                else:
                    hits = pd.DataFrame()
                if not hits.empty:
                    st.write("**{:,} contracts found**".format(len(hits)))
                    hits["contract_amount_jmd"] = pd.to_numeric(hits.get("contract_amount_jmd",0), errors="coerce").fillna(0)
                    st.write("**Total Value:** " + fmt_jmd(hits["contract_amount_jmd"].sum()))
                    show_c = [c for c in ["title","procuring_entity","contract_amount_jmd","publication_date"] if c in hits.columns]
                    st.dataframe(hits[show_c].head(10), use_container_width=True)
                else:
                    st.info("No matching contracts in current dataset.")

# ════════════════════════════════════════════════════════════
# TAB 9 — OPPORTUNITIES (OPEN BIDS)
# ════════════════════════════════════════════════════════════
with tabs[8]:
    st.header("Live Opportunities — Open Bids")
    df_b = bids_df.copy()
    if df_b.empty:
        st.warning("No bid data. Run the scraper.")
    else:
        col1, col2, col3 = st.columns(3)
        opp_search = col1.text_input("Search bids", key="opp_search")
        opp_status = col2.selectbox("Status", ["All"] + sorted(df_b.get("status",pd.Series()).dropna().unique().tolist()), key="opp_status")
        opp_cat    = col3.selectbox("Category", ["All Categories"] + CATEGORY_LIST, key="opp_cat")

        fdf_b = df_b.copy()
        if opp_search:
            mask = fdf_b.apply(lambda r: opp_search.lower() in str(r).lower(), axis=1)
            fdf_b = fdf_b[mask]
        if opp_status != "All":
            fdf_b = fdf_b[fdf_b["status"] == opp_status]
        if opp_cat != "All Categories" and "normalized_category" in fdf_b.columns:
            fdf_b = fdf_b[fdf_b["normalized_category"] == opp_cat]

        st.metric("Matching Opportunities", "{:,}".format(len(fdf_b)))
        show_bid_cols = [c for c in ["cft_title","procuring_entity","reference_number","submission_deadline","status","normalized_category","opened_bids_url"] if c in fdf_b.columns]
        st.dataframe(fdf_b[show_bid_cols].head(200), use_container_width=True)
        st.download_button("Export Opportunities", fdf_b.to_csv(index=False), "opportunities.csv", "text/csv")

# ════════════════════════════════════════════════════════════
# TAB 10 — DATA AUDIT
# ════════════════════════════════════════════════════════════
with tabs[9]:
    st.header("Data Audit Panel")
    df = awards_df.copy()
    df_b = bids_df.copy()

    st.subheader("Awards Data Quality")
    if not df.empty:
        total = len(df)
        null_amount = df["contract_amount_jmd"].isna().sum() if "contract_amount_jmd" in df.columns else 0
        null_date   = df["publication_date"].isna().sum() if "publication_date" in df.columns else 0
        null_entity = df["procuring_entity"].isna().sum() if "procuring_entity" in df.columns else 0
        uncat       = (df["normalized_category"] == "Uncategorized").sum() if "normalized_category" in df.columns else 0
        dupes       = df.duplicated(subset=["procuring_entity","title","publication_date"]).sum() if all(c in df.columns for c in ["procuring_entity","title","publication_date"]) else 0

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("Total Awards", "{:,}".format(total))
        c2.metric("Null Amounts", "{:,}".format(int(null_amount)))
        c3.metric("Null Dates", "{:,}".format(int(null_date)))
        c4.metric("Null Buyers", "{:,}".format(int(null_entity)))
        c5.metric("Uncategorized", "{:,}".format(int(uncat)))
        c6.metric("Duplicates", "{:,}".format(int(dupes)))

        # Category confidence distribution
        if "category_confidence" in df.columns:
            st.subheader("Category Confidence Distribution")
            fig = px.histogram(df, x="category_confidence", nbins=20, color_discrete_sequence=["#2ECC71"])
            fig.update_layout(height=260)
            st.plotly_chart(fig, use_container_width=True)

        # Unique entities
        st.subheader("Unique Procurement Methods")
        if "procurement_method" in df.columns:
            st.write(df["procurement_method"].value_counts())
    else:
        st.info("No award data loaded.")

    st.subheader("Opened Bids Data Quality")
    if not df_b.empty:
        b1,b2,b3 = st.columns(3)
        b1.metric("Total Bids", "{:,}".format(len(df_b)))
        b2.metric("Null Deadlines", "{:,}".format(int(df_b["submission_deadline"].isna().sum()) if "submission_deadline" in df_b.columns else 0))
        b3.metric("Unique Buyers", "{:,}".format(df_b["procuring_entity"].nunique() if "procuring_entity" in df_b.columns else 0))
    else:
        st.info("No bid data loaded.")

    # Audit log from DB
    st.subheader("Scraper Run History")
    try:
        from database.db import get_engine
        al = pd.read_sql("SELECT * FROM audit_log ORDER BY run_at DESC LIMIT 20", get_engine())
        if al.empty:
            st.info("No scraper runs logged yet.")
        else:
            st.dataframe(al, use_container_width=True)
    except:
        st.info("Audit log will appear after first scraper run.")
