"""Jamaica Procurement OS v3 — 20-tab dashboard"""
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
from utils.analytics import (compute_win_rates, geo_summary, find_similar_tenders,
    predict_next_procurement, build_relationship_graph, detect_repeat_relationships,
    get_source_registry, add_parish_column)

st.set_page_config(page_title="Jamaica Procurement OS", page_icon="JA", layout="wide")
st.markdown("""<style>[data-testid="stMetricValue"]{font-size:1.5rem;font-weight:700;}
.insight-card{background:#1E1E2E;border-left:4px solid #F39C12;padding:10px 14px;border-radius:5px;margin:5px 0;}
.insight-high{border-left-color:#E74C3C;}.insight-medium{border-left-color:#F39C12;}.insight-low{border-left-color:#3498DB;}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data():
    awards, bids = pd.DataFrame(), pd.DataFrame()
    try:
        from database.db import get_engine, init_db
        init_db()
        engine = get_engine()
        awards = pd.read_sql("SELECT * FROM contract_awards", engine)
        bids   = pd.read_sql("SELECT * FROM opened_bids", engine)
    except Exception:
        pass
    base = os.path.join(os.path.dirname(__file__), "..", "data")
    if awards.empty:
        try: awards = pd.read_csv(os.path.join(base, "sample_awards.csv"))
        except: pass
    if bids.empty:
        try: bids = pd.read_csv(os.path.join(base, "sample_bids.csv"))
        except: pass
    for col in ["contract_amount_jmd"]:
        if col in awards.columns:
            awards[col] = awards[col].apply(clean_amount)
    for col in ["publication_date"]:
        if col in awards.columns:
            awards[col] = awards[col].apply(clean_date)
    for col in ["submission_deadline","award_date"]:
        if col in bids.columns:
            bids[col] = bids[col].apply(clean_date)
    if "normalized_category" not in awards.columns or awards["normalized_category"].isna().all():
        awards[["normalized_category","category_confidence"]] = awards.get("title",pd.Series([""]*len(awards))).apply(lambda t: pd.Series(classify_category(t)))
    if "normalized_category" not in bids.columns or bids["normalized_category"].isna().all():
        bids[["normalized_category","category_confidence"]] = bids.get("cft_title",pd.Series([""]*len(bids))).apply(lambda t: pd.Series(classify_category(t)))
    return awards, bids

@st.cache_data(ttl=300)
def load_watchlist():
    try:
        from database.db import get_engine
        return pd.read_sql("SELECT * FROM watchlists", get_engine())
    except:
        return pd.DataFrame(columns=["id","watch_type","watch_value","created_at"])

awards_df, bids_df = load_data()

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/4/43/Flag_of_Jamaica.svg", width=80)
    st.title("Jamaica Procurement OS")
    st.caption("Private Beta v3")
    st.markdown("---")
    st.metric("Awards", "{:,}".format(len(awards_df)))
    st.metric("Bids", "{:,}".format(len(bids_df)))
    if "contract_amount_jmd" in awards_df.columns:
        st.metric("Total Value", fmt_jmd(pd.to_numeric(awards_df["contract_amount_jmd"],errors="coerce").sum()))
    st.markdown("---")
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    with st.expander("Admin: GOJEP Scraper"):
        _max_pages = st.number_input("Max pages (0 = all ~1231)", min_value=0, max_value=2000, value=2, step=1)
        if st.button("Run scraper now", use_container_width=True):
            try:
                from scrapers.awards_scraper import scrape_awards
                _mp = int(_max_pages) if int(_max_pages) > 0 else 2000
                with st.spinner("Scraping GOJEP Contract Award Notices..."):
                    _summary = scrape_awards(max_pages=_mp)
                st.success("{}: {} new of {} seen across {} pages.".format(_summary.get("status"), _summary.get("rows_new"), _summary.get("rows_seen"), _summary.get("pages_fetched")))
                st.cache_data.clear()
            except Exception as _e:
                st.error("Scraper failed: {}".format(_e))
        try:
            from database.db import get_engine
            from sqlalchemy import text as _sql_text
            with get_engine().connect() as _c:
                _r = _c.execute(_sql_text("SELECT status, pages_fetched, rows_new, total_available, finished_at FROM scraper_runs ORDER BY id DESC LIMIT 1")).fetchone()
            if _r:
                st.caption("Last run: {} | {} new | {} pages | of {} total | {}".format(_r[0], _r[2], _r[1], _r[3], _r[4]))
            else:
                st.caption("No scraper runs yet.")
        except Exception:
            st.caption("No run history yet.")

# ── 20 TABS ──────────────────────────────────────────────
tabs = st.tabs([
    "Overview","Category Intel","Supplier Intel","Benchmark","Seasonality",
    "Competition","Insights","Watchlist","Opportunities","Audit",
    "PDF Parser","Auto-Scraper","Alerts","Compliance Vault","Win Rate",
    "Geo Map","Similar Tenders","Budget Predictor","Source Registry","Relationship Graph"
])

# ════ TAB 1: OVERVIEW ════
with tabs[0]:
    st.header("Overview")
    df = awards_df.copy()
    if df.empty:
        st.warning("No award data. Run the scraper.")
    else:
        df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd",0), errors="coerce").fillna(0)
        total = df["contract_amount_jmd"].sum()
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Awards", "{:,}".format(len(df)))
        c2.metric("Total Value", fmt_jmd(total))
        c3.metric("Unique Buyers", df["procuring_entity"].nunique() if "procuring_entity" in df.columns else 0)
        c4.metric("Open Bids", len(bids_df))
        if "publication_date" in df.columns:
            df["pub_dt"] = pd.to_datetime(df["publication_date"], errors="coerce")
            monthly = df.dropna(subset=["pub_dt"]).groupby(df["pub_dt"].dt.to_period("M").astype(str)).agg(count=("id","count"),value=("contract_amount_jmd","sum")).reset_index()
            monthly.columns = ["Month","Count","Value"]
            col1,col2 = st.columns(2)
            with col1:
                st.subheader("Awards by Month")
                fig = px.bar(monthly,x="Month",y="Count",color_discrete_sequence=["#F39C12"])
                fig.update_layout(height=280,margin=dict(t=10,b=40))
                st.plotly_chart(fig,use_container_width=True)
            with col2:
                st.subheader("Value by Month")
                fig2 = px.bar(monthly,x="Month",y="Value",color_discrete_sequence=["#2ECC71"])
                fig2.update_layout(height=280,margin=dict(t=10,b=40))
                st.plotly_chart(fig2,use_container_width=True)
        if "procuring_entity" in df.columns:
            col3,col4 = st.columns(2)
            with col3:
                st.subheader("Top 10 by Value")
                tv = df.groupby("procuring_entity")["contract_amount_jmd"].sum().nlargest(10).reset_index()
                tv.columns=["Buyer","Total"]
                st.plotly_chart(px.bar(tv,x="Total",y="Buyer",orientation="h",color_discrete_sequence=["#9B59B6"],height=320),use_container_width=True)
            with col4:
                st.subheader("Top 10 by Count")
                tc = df.groupby("procuring_entity").size().nlargest(10).reset_index()
                tc.columns=["Buyer","Count"]
                st.plotly_chart(px.bar(tc,x="Count",y="Buyer",orientation="h",color_discrete_sequence=["#E74C3C"],height=320),use_container_width=True)
        st.subheader("Search & Export")
        col7,col8 = st.columns([3,1])
        kw = col7.text_input("Search",key="ov_search")
        buyers_list = ["All"]+sorted(df.get("procuring_entity",pd.Series()).dropna().unique().tolist())
        sb = col8.selectbox("Buyer",buyers_list,key="ov_buyer")
        fdf = df[df.apply(lambda r: kw.lower() in str(r).lower(), axis=1)] if kw else df
        if sb != "All": fdf = fdf[fdf["procuring_entity"]==sb]
        st.dataframe(fdf.head(200),use_container_width=True)
        st.download_button("Export CSV",fdf.to_csv(index=False),"awards.csv","text/csv")

# ════ TAB 2: CATEGORY INTEL ════
with tabs[1]:
    st.header("Category Intelligence Engine")
    df=awards_df.copy()
    df["contract_amount_jmd"]=pd.to_numeric(df.get("contract_amount_jmd",0),errors="coerce").fillna(0)
    if "normalized_category" not in df.columns:
        df[["normalized_category","category_confidence"]]=df.get("title",pd.Series([""]*len(df))).apply(lambda t:pd.Series(classify_category(t)))
    cv=df.groupby("normalized_category")["contract_amount_jmd"].sum().sort_values(ascending=False).reset_index()
    cc=df.groupby("normalized_category").size().reset_index(name="count")
    cm=cv.merge(cc,on="normalized_category");cm.columns=["Category","Total Value","Count"]
    c1,c2=st.columns(2)
    with c1:
        fig=px.bar(cm.head(15),x="Total Value",y="Category",orientation="h",color="Category",color_discrete_map=CATEGORY_COLORS,height=400)
        fig.update_layout(showlegend=False);st.plotly_chart(fig,use_container_width=True)
    with c2:
        fig2=px.pie(cm.head(12),values="Count",names="Category",color="Category",color_discrete_map=CATEGORY_COLORS,height=400)
        st.plotly_chart(fig2,use_container_width=True)
    if "publication_date" in df.columns:
        df["pub_dt"]=pd.to_datetime(df["publication_date"],errors="coerce")
        sel_cats=st.multiselect("Category growth",CATEGORY_LIST,default=CATEGORY_LIST[:5],key="cg")
        if sel_cats:
            cgdf=df[df["normalized_category"].isin(sel_cats)].dropna(subset=["pub_dt"])
            cgdf["Month"]=cgdf["pub_dt"].dt.to_period("M").astype(str)
            cg=cgdf.groupby(["Month","normalized_category"]).size().reset_index(name="count")
            st.plotly_chart(px.line(cg,x="Month",y="count",color="normalized_category",color_discrete_map=CATEGORY_COLORS,markers=True,height=300),use_container_width=True)
    st.dataframe(cm,use_container_width=True)

# ════ TAB 3: SUPPLIER INTEL ════
with tabs[2]:
    st.header("Supplier Intelligence")
    df=awards_df.copy();df["contract_amount_jmd"]=pd.to_numeric(df.get("contract_amount_jmd",0),errors="coerce").fillna(0)
    sup_df=pd.DataFrame()
    try:
        from database.db import get_engine
        sup_df=pd.read_sql("SELECT * FROM suppliers",get_engine())
    except: pass
    if sup_df.empty and "supplier_name" in df.columns:
        sdf=df[df["supplier_name"].notna()&(df["supplier_name"]!="")].copy()
        if not sdf.empty:
            sup_df=sdf.groupby("supplier_name").agg(award_count=("id","count"),total_award_value=("contract_amount_jmd","sum"),avg_award_value=("contract_amount_jmd","mean")).reset_index()
    if sup_df.empty:
        st.info("No supplier data yet — builds as scraper runs.")
    else:
        for col in ["total_award_value","award_count","avg_award_value"]:
            if col in sup_df.columns: sup_df[col]=pd.to_numeric(sup_df[col],errors="coerce").fillna(0)
        c1,c2,c3=st.columns(3)
        c1.metric("Suppliers","{:,}".format(len(sup_df)));c2.metric("Total Awards","{:,}".format(int(sup_df["award_count"].sum())));c3.metric("Avg Contract",fmt_jmd(sup_df["avg_award_value"].mean()))
        top_s=sup_df.nlargest(15,"total_award_value")
        st.plotly_chart(px.bar(top_s,x="total_award_value",y="supplier_name",orientation="h",color_discrete_sequence=["#9B59B6"],height=400),use_container_width=True)
        sq=st.text_input("Search supplier",key="ss")
        if sq:
            res=sup_df[sup_df["supplier_name"].str.contains(sq,case=False,na=False)]
            for _,r in res.head(5).iterrows():
                with st.expander(r["supplier_name"]):
                    st.write("Wins: {:,} | Value: {} | Avg: {}".format(int(r["award_count"]),fmt_jmd(r["total_award_value"]),fmt_jmd(r["avg_award_value"])))
        st.dataframe(sup_df.sort_values("total_award_value",ascending=False),use_container_width=True)
        st.download_button("Export",sup_df.to_csv(index=False),"suppliers.csv","text/csv")

# ════ TAB 4: BENCHMARK ════
with tabs[3]:
    st.header("Price Benchmark Engine")
    df=awards_df.copy();df["contract_amount_jmd"]=pd.to_numeric(df.get("contract_amount_jmd",0),errors="coerce");df=df[df["contract_amount_jmd"]>0]
    if df.empty: st.warning("No contract amount data.")
    else:
        c1,c2=st.columns(2)
        buyers=["All Buyers"]+sorted(df.get("procuring_entity",pd.Series()).dropna().unique().tolist())
        cats=["All Categories"]+CATEGORY_LIST
        sb=c1.selectbox("Buyer",buyers,key="bm_b");sc=c2.selectbox("Category",cats,key="bm_c")
        bm=df.copy()
        if sb!="All Buyers": bm=bm[bm["procuring_entity"]==sb]
        if sc!="All Categories" and "normalized_category" in bm.columns: bm=bm[bm["normalized_category"]==sc]
        if bm.empty: st.info("No matching contracts.")
        else:
            a=bm["contract_amount_jmd"].dropna()
            c1,c2,c3,c4,c5=st.columns(5)
            c1.metric("Min",fmt_jmd(a.min()));c2.metric("Max",fmt_jmd(a.max()));c3.metric("Median",fmt_jmd(a.median()));c4.metric("Mean",fmt_jmd(a.mean()));c5.metric("Count","{:,}".format(len(a)))
            st.plotly_chart(px.histogram(bm,x="contract_amount_jmd",nbins=30,color_discrete_sequence=["#F39C12"],height=260),use_container_width=True)
            bins=[0,1e6,5e6,20e6,100e6,500e6,1e13];labels=["<1M","1-5M","5-20M","20-100M","100-500M",">500M"]
            bm["band"]=pd.cut(bm["contract_amount_jmd"],bins=bins,labels=labels)
            bc=bm["band"].value_counts().sort_index().reset_index();bc.columns=["Band","Count"]
            st.plotly_chart(px.bar(bc,x="Band",y="Count",color_discrete_sequence=["#9B59B6"],height=240),use_container_width=True)

# ════ TAB 5: SEASONALITY ════
with tabs[4]:
    st.header("Buyer Seasonality Engine")
    df=awards_df.copy();df["contract_amount_jmd"]=pd.to_numeric(df.get("contract_amount_jmd",0),errors="coerce").fillna(0)
    if df.empty or "procuring_entity" not in df.columns: st.warning("No data.")
    else:
        sel=st.selectbox("Select Buyer",sorted(df["procuring_entity"].dropna().unique().tolist()),key="sea")
        sdf=df[df["procuring_entity"]==sel].copy()
        if "publication_date" in sdf.columns:
            sdf["pub_dt"]=pd.to_datetime(sdf["publication_date"],errors="coerce");sdf=sdf.dropna(subset=["pub_dt"])
            sdf["MonthName"]=sdf["pub_dt"].dt.strftime("%b");sdf["Year"]=sdf["pub_dt"].dt.year
            c1,c2=st.columns(2)
            c1.metric("Contracts","{:,}".format(len(sdf)));c2.metric("Total Spend",fmt_jmd(sdf["contract_amount_jmd"].sum()))
            mc=sdf.groupby(["Year","MonthName"]).size().reset_index(name="count")
            st.plotly_chart(px.density_heatmap(mc,x="MonthName",y="Year",z="count",color_continuous_scale="YlOrRd",height=280),use_container_width=True)
            mo=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            mv=sdf.groupby("MonthName")["contract_amount_jmd"].sum().reset_index()
            mv["MonthName"]=pd.Categorical(mv["MonthName"],categories=mo,ordered=True);mv=mv.sort_values("MonthName")
            st.plotly_chart(px.bar(mv,x="MonthName",y="contract_amount_jmd",color_discrete_sequence=["#3498DB"],height=240),use_container_width=True)

# ════ TAB 6: COMPETITION ════
with tabs[5]:
    st.header("Competition Density Engine")
    comp_df=pd.DataFrame()
    try:
        from database.db import get_engine
        comp_df=pd.read_sql("SELECT * FROM competition_metrics",get_engine())
    except: pass
    if comp_df.empty and not bids_df.empty and "bidder_count" in bids_df.columns:
        bdf=bids_df.copy();bdf["bidder_count"]=pd.to_numeric(bdf["bidder_count"],errors="coerce");bdf=bdf[bdf["bidder_count"]>0]
        if not bdf.empty:
            comp_df=bdf.groupby("normalized_category")["bidder_count"].agg(avg_bidders="mean",total_tenders="count").reset_index()
    if not comp_df.empty and "avg_bidders" in comp_df.columns:
        comp_df["avg_bidders"]=pd.to_numeric(comp_df["avg_bidders"],errors="coerce")
        cat_col="normalized_category" if "normalized_category" in comp_df.columns else "category"
        c1,c2=st.columns(2)
        with c1:
            st.plotly_chart(px.bar(comp_df.sort_values("avg_bidders",ascending=False),x="avg_bidders",y=cat_col,orientation="h",color_discrete_sequence=["#E07B39"],height=380),use_container_width=True)
        with c2:
            lo=comp_df[comp_df["avg_bidders"]<=3].sort_values("avg_bidders");hi=comp_df[comp_df["avg_bidders"]>5].sort_values("avg_bidders",ascending=False)
            st.markdown("**Low Competition (<=3 bidders)**");st.dataframe(lo[[cat_col,"avg_bidders"]].head(8),use_container_width=True)
            st.markdown("**High Competition (>5 bidders)**");st.dataframe(hi[[cat_col,"avg_bidders"]].head(8),use_container_width=True)
    else:
        st.info("Competition data populates as bid opening PDFs are parsed.")
        df=awards_df.copy()
        if "procurement_method" in df.columns:
            pm=df["procurement_method"].value_counts().reset_index();pm.columns=["Method","Count"]
            st.plotly_chart(px.bar(pm,x="Count",y="Method",orientation="h",color_discrete_sequence=["#16A085"],height=300),use_container_width=True)

# ════ TAB 7: INSIGHTS ════
with tabs[6]:
    st.header("Auto-Generated Intelligence Insights")
    insights=generate_insights(awards_df,bids_df)
    for ins in insights:
        sev=ins.get("severity","medium");icon=ins.get("icon","I");headline=ins.get("headline","");detail=ins.get("detail","")
        st.markdown("<div class='insight-card insight-{s}'><strong>[{i}]</strong> {h}<br><small>{d}</small></div>".format(s=sev,i=icon,h=headline,d=detail),unsafe_allow_html=True)

# ════ TAB 8: WATCHLIST ════
with tabs[7]:
    st.header("Watchlist")
    w1,w2=st.columns([2,1])
    wt=w1.selectbox("Watch type",["buyer","supplier","category"],key="wl_t")
    wv=w2.text_input("Value",key="wl_v")
    if st.button("Add to Watchlist",key="wl_add"):
        if wv.strip():
            try:
                from database.db import get_engine,add_watchlist
                with get_engine().begin() as conn: add_watchlist(conn,wt,wv.strip())
                st.success("Added: {} — {}".format(wt,wv));st.cache_data.clear()
            except Exception as e: st.error(str(e))
    wl=load_watchlist()
    if wl.empty: st.info("Watchlist empty. Add items above.")
    else:
        for _,row in wl.iterrows():
            with st.expander("{} — {}".format(row["watch_type"].upper(),row["watch_value"])):
                dfw=awards_df.copy()
                if row["watch_type"]=="buyer" and "procuring_entity" in dfw.columns:
                    hits=dfw[dfw["procuring_entity"].str.contains(row["watch_value"],case=False,na=False)]
                elif row["watch_type"]=="category" and "normalized_category" in dfw.columns:
                    hits=dfw[dfw["normalized_category"]==row["watch_value"]]
                else: hits=pd.DataFrame()
                if not hits.empty:
                    hits["contract_amount_jmd"]=pd.to_numeric(hits.get("contract_amount_jmd",0),errors="coerce").fillna(0)
                    st.write("**{:,} contracts | Total: {}**".format(len(hits),fmt_jmd(hits["contract_amount_jmd"].sum())))
                    sc=[c for c in ["title","procuring_entity","contract_amount_jmd","publication_date"] if c in hits.columns]
                    st.dataframe(hits[sc].head(10),use_container_width=True)

# ════ TAB 9: OPPORTUNITIES ════
with tabs[8]:
    st.header("Live Opportunities")
    dfb=bids_df.copy()
    if dfb.empty: st.warning("No bid data.")
    else:
        c1,c2,c3=st.columns(3)
        qs=c1.text_input("Search",key="opp_s");ostatus=c2.selectbox("Status",["All"]+sorted(dfb.get("status",pd.Series()).dropna().unique().tolist()),key="opp_st");ocat=c3.selectbox("Category",["All"]+CATEGORY_LIST,key="opp_cat")
        fdfb=dfb.copy()
        if qs: fdfb=fdfb[fdfb.apply(lambda r:qs.lower() in str(r).lower(),axis=1)]
        if ostatus!="All": fdfb=fdfb[fdfb["status"]==ostatus]
        if ocat!="All" and "normalized_category" in fdfb.columns: fdfb=fdfb[fdfb["normalized_category"]==ocat]
        st.metric("Matching","{:,}".format(len(fdfb)))
        sc=[c for c in ["cft_title","procuring_entity","reference_number","submission_deadline","status","normalized_category"] if c in fdfb.columns]
        st.dataframe(fdfb[sc].head(200),use_container_width=True)
        st.download_button("Export",fdfb.to_csv(index=False),"opportunities.csv","text/csv")

# ════ TAB 10: AUDIT ════
with tabs[9]:
    st.header("Data Audit Panel")
    df=awards_df.copy();dfb=bids_df.copy()
    if not df.empty:
        null_a=df["contract_amount_jmd"].isna().sum() if "contract_amount_jmd" in df.columns else 0
        null_d=df["publication_date"].isna().sum() if "publication_date" in df.columns else 0
        uncat=(df["normalized_category"]=="Uncategorized").sum() if "normalized_category" in df.columns else 0
        dupes=df.duplicated(subset=["procuring_entity","title","publication_date"]).sum() if all(c in df.columns for c in ["procuring_entity","title","publication_date"]) else 0
        c1,c2,c3,c4,c5=st.columns(5)
        c1.metric("Total","{:,}".format(len(df)));c2.metric("Null $","{:,}".format(int(null_a)));c3.metric("Null Date","{:,}".format(int(null_d)));c4.metric("Uncat","{:,}".format(int(uncat)));c5.metric("Dupes","{:,}".format(int(dupes)))
        if "category_confidence" in df.columns:
            st.plotly_chart(px.histogram(df,x="category_confidence",nbins=20,color_discrete_sequence=["#2ECC71"],height=220),use_container_width=True)
    if not dfb.empty:
        b1,b2=st.columns(2);b1.metric("Bids","{:,}".format(len(dfb)));b2.metric("Null Deadlines","{:,}".format(int(dfb["submission_deadline"].isna().sum()) if "submission_deadline" in dfb.columns else 0))
    try:
        from database.db import get_engine
        al=pd.read_sql("SELECT * FROM audit_log ORDER BY run_at DESC LIMIT 20",get_engine())
        if not al.empty: st.dataframe(al,use_container_width=True)
        else: st.info("No scraper runs logged.")
    except: st.info("Audit log available after first scraper run.")

# ════ TAB 11: PDF PARSER ════
with tabs[10]:
    st.header("PDF Bid Opening Parser — Feature 1")
    st.caption("Extract supplier names and bidder counts from GOJEP bid opening PDFs.")
    pdf_url = st.text_input("Paste a bid opening PDF URL from GOJEP", key="pdf_url", placeholder="https://www.gojep.gov.jm/epps/...")
    if st.button("Parse PDF", key="pdf_go"):
        if not pdf_url.strip():
            st.warning("Enter a PDF URL.")
        else:
            with st.spinner("Downloading and parsing PDF..."):
                try:
                    from scrapers.pdf_parser import parse_bid_opening_pdf
                    result = parse_bid_opening_pdf(pdf_url.strip())
                    if result.get("error"):
                        st.error("Parse error: " + result["error"])
                    else:
                        st.success("{} bidders extracted".format(result["bidder_count"]))
                        if result["bidders"]:
                            bdf = pd.DataFrame(result["bidders"])
                            bdf.columns = [c.replace("_"," ").title() for c in bdf.columns]
                            st.dataframe(bdf, use_container_width=True)
                        else:
                            st.info("No bidder names matched extraction patterns.")
                        if result["raw_text_preview"]:
                            with st.expander("Raw text preview (first 500 chars)"):
                                st.code(result["raw_text_preview"])
                except ImportError:
                    st.error("pdfplumber not installed. Add to requirements.txt and redeploy.")
    st.markdown("---")
    st.subheader("Batch PDF Enrichment")
    st.caption("Automatically parse bid opening PDFs from the opened bids table to extract bidder counts.")
    max_p = st.number_input("Max PDFs to parse (rate-limited at 1.5s each)", min_value=1, max_value=200, value=20, key="max_pdfs")
    if st.button("Run Batch PDF Enrichment", key="pdf_batch"):
        with st.spinner("Parsing up to {} PDFs...".format(max_p)):
            try:
                from scrapers.pdf_parser import enrich_bids_with_pdf_data
                enriched = enrich_bids_with_pdf_data(bids_df, max_pdfs=int(max_p))
                new_count = (enriched["bidder_count"] > 0).sum() if "bidder_count" in enriched.columns else 0
                st.success("Enriched {} bids with bidder data.".format(new_count))
                st.dataframe(enriched[enriched.get("bidder_count",pd.Series(dtype=int)) > 0].head(50), use_container_width=True)
            except Exception as e:
                st.error(str(e))

# ════ TAB 12: AUTO-SCRAPER ════
with tabs[11]:
    st.header("Auto-Scraper — Feature 2")
    st.caption("GitHub Actions runs the scraper daily at 03:00 UTC (10:00 PM Jamaica time).")
    st.info("Workflow file committed: `.github/workflows/scraper.yml`")
    st.markdown("""
**Scheduled:** Daily at 03:00 UTC
**Trigger:** Also manually triggerable from GitHub Actions tab
**What it does:**
1. Checks out the repository
2. Installs Python dependencies
3. Runs `python run_scrapers.py --max-pages 50`
4. Commits updated `procurement.db` back to the repo
5. Uploads DB as a downloadable artifact for debugging

**To trigger manually:**
1. Go to your GitHub repo
2. Click **Actions** tab
3. Select **Daily Procurement Scraper**
4. Click **Run workflow**
    """)
    st.subheader("Scraper Run History")
    try:
        from database.db import get_engine
        al = pd.read_sql("SELECT * FROM audit_log ORDER BY run_at DESC LIMIT 10", get_engine())
        if al.empty: st.info("No runs yet. Trigger a manual run from GitHub Actions.")
        else: st.dataframe(al, use_container_width=True)
    except: st.info("Connect DB to see scraper history.")

# ════ TAB 13: ALERTS ════
with tabs[12]:
    st.header("Watchlist Alert Engine — Feature 3")
    st.caption("Configure email alerts for watchlist matches. Runs automatically after each scraper run.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Email Configuration")
        st.code("""# Set these environment variables in Streamlit Secrets or .env:\nALERT_EMAIL_FROM=your@gmail.com\nALERT_EMAIL_PASS=your_app_password\nALERT_EMAIL_TO=recipient@email.com\nSMTP_HOST=smtp.gmail.com  # default\nSMTP_PORT=587             # default""", language="bash")
        st.markdown("**Gmail Setup:** Enable 2FA, then generate an App Password at myaccount.google.com/apppasswords")
    with col2:
        st.subheader("Test Alert Now")
        test_hours = st.number_input("Look back N hours for new records", min_value=1, max_value=720, value=25, key="alert_hrs")
        if st.button("Check Watchlist & Preview Alerts", key="alert_test"):
            try:
                from utils.alerts import check_watchlist_hits
                wl = load_watchlist()
                hits = check_watchlist_hits(awards_df, bids_df, wl, lookback_hours=int(test_hours))
                if hits:
                    st.success("{} watchlist matches found!".format(len(hits)))
                    st.dataframe(pd.DataFrame(hits), use_container_width=True)
                else:
                    st.info("No matches in the last {} hours.".format(test_hours))
            except Exception as e:
                st.error(str(e))
    st.markdown("---")
    st.subheader("Alert Log")
    st.info("Full alert history will appear here after email sends are implemented.")

# ════ TAB 14: COMPLIANCE VAULT ════
with tabs[13]:
    st.header("Compliance Vault — Feature 4")
    st.caption("Store and track supplier compliance documents: TRN, TCC, NCC, Insurance.")
    st.info("Architecture ready. Data entry UI below. Full document upload requires file storage integration (S3/Cloudinary).")
    with st.form("compliance_form"):
        st.subheader("Add / Update Supplier Profile")
        c1,c2 = st.columns(2)
        cname  = c1.text_input("Company Name")
        trn    = c2.text_input("TRN (Tax Registration Number)")
        tcc    = c1.date_input("TCC Expiry Date")
        ncc    = c2.selectbox("NCC Status", ["Active","Inactive","Pending","Unknown"])
        ins    = c1.date_input("Insurance Expiry Date")
        refs   = c2.number_input("Reference Letters Count", min_value=0, max_value=20, step=1)
        cats_v = st.text_input("Categories (comma-separated)", placeholder="Cleaning, Security, ICT")
        submitted = st.form_submit_button("Save Profile")
        if submitted and cname.strip():
            try:
                from database.db import get_engine, supplier_profiles_table
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                from datetime import timezone
                row = {
                    "company_name": cname.strip(),
                    "trn": trn.strip(),
                    "tcc_expiry": str(tcc),
                    "ncc_status": ncc,
                    "insurance_expiry": str(ins),
                    "reference_letters_count": int(refs),
                    "categories": cats_v.strip(),
                    "document_urls": "[]",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
                stmt = sqlite_insert(supplier_profiles_table).values(**row)
                stmt = stmt.on_conflict_do_update(index_elements=["company_name"], set_={"updated_at": row["updated_at"], "ncc_status": row["ncc_status"], "tcc_expiry": row["tcc_expiry"]})
                with get_engine().begin() as conn:
                    conn.execute(stmt)
                st.success("Profile saved for: " + cname)
            except Exception as e:
                st.error(str(e))
    st.subheader("Supplier Profile Register")
    try:
        from database.db import get_engine
        profiles = pd.read_sql("SELECT company_name,trn,tcc_expiry,ncc_status,insurance_expiry,reference_letters_count,categories FROM supplier_profiles", get_engine())
        if profiles.empty: st.info("No profiles yet.")
        else: st.dataframe(profiles, use_container_width=True)
    except: st.info("Profile register will appear after first entry.")

# ════ TAB 15: WIN RATE ════
with tabs[14]:
    st.header("Bid Win Rate Calculator — Feature 5")
    st.caption("Cross-reference suppliers in bids vs awards to compute win rates.")
    with st.spinner("Computing win rates..."):
        wr_df = compute_win_rates(awards_df, bids_df)
    if wr_df.empty:
        st.info("Win rate analysis requires supplier_name data in awards and supplier_names_extracted in bids. Populates as PDF parser runs.")
    else:
        c1,c2,c3 = st.columns(3)
        c1.metric("Suppliers Tracked", "{:,}".format(len(wr_df)))
        avg_wr = wr_df["win_rate_pct"].dropna().mean()
        c2.metric("Avg Win Rate", "{:.1f}%".format(avg_wr) if not np.isnan(avg_wr) else "N/A")
        c3.metric("Total Value Won", fmt_jmd(wr_df["total_value_won"].sum()))
        top_winners = wr_df.nlargest(15, "total_value_won")
        st.subheader("Top Suppliers by Value Won")
        st.plotly_chart(px.bar(top_winners, x="total_value_won", y="supplier", orientation="h", color_discrete_sequence=["#27AE60"], height=380), use_container_width=True)
        st.subheader("Win Rate Leaderboard")
        wr_display = wr_df[wr_df["win_rate_pct"].notna()].nlargest(20, "win_rate_pct")
        st.dataframe(wr_display, use_container_width=True)
        st.download_button("Export Win Rate Data", wr_df.to_csv(index=False), "win_rates.csv", "text/csv")

# ════ TAB 16: GEO MAP ════
with tabs[15]:
    st.header("Geo-Intelligence: Parish Spend Map — Feature 6")
    st.caption("Maps procuring entities to Jamaican parishes based on name keywords.")
    df = awards_df.copy()
    df["contract_amount_jmd"] = pd.to_numeric(df.get("contract_amount_jmd",0), errors="coerce").fillna(0)
    geo_df = geo_summary(df)
    if geo_df.empty:
        st.warning("No geo data.")
    else:
        c1,c2,c3 = st.columns(3)
        c1.metric("Parishes with Data", "{:,}".format((geo_df["parish"]!="Unknown").sum()))
        top_parish = geo_df[geo_df["parish"]!="Unknown"].iloc[0]["parish"] if not geo_df[geo_df["parish"]!="Unknown"].empty else "N/A"
        c2.metric("Top Spending Parish", top_parish)
        c3.metric("Total Value Mapped", fmt_jmd(geo_df["total_value"].sum()))
        st.subheader("Award Value by Parish")
        gf = geo_df[geo_df["parish"]!="Unknown"].copy()
        st.plotly_chart(px.bar(gf, x="total_value", y="parish", orientation="h", color_discrete_sequence=["#E07B39"], height=380), use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Awards by Parish")
            st.plotly_chart(px.pie(gf, values="award_count", names="parish", height=320), use_container_width=True)
        with col2:
            st.subheader("Unique Buyers by Parish")
            st.plotly_chart(px.bar(gf.sort_values("unique_buyers", ascending=False), x="parish", y="unique_buyers", color_discrete_sequence=["#8E44AD"], height=300), use_container_width=True)
        st.dataframe(geo_df, use_container_width=True)

# ════ TAB 17: SIMILAR TENDERS ════
with tabs[16]:
    st.header("Similar Tender Finder — Feature 7")
    st.caption("Find historically similar contracts using TF-IDF text similarity. No AI needed.")
    query = st.text_input("Describe the tender you are preparing for:", placeholder="e.g. janitorial cleaning services government office", key="sim_q")
    top_n = st.slider("Number of results", 5, 30, 10, key="sim_n")
    if st.button("Find Similar Tenders", key="sim_go") and query.strip():
        with st.spinner("Scanning {} contracts...".format(len(awards_df))):
            results = find_similar_tenders(query.strip(), awards_df, top_n=top_n)
        if results.empty:
            st.info("No results found.")
        else:
            st.success("{} similar contracts found.".format(len(results)))
            if "similarity_score" in results.columns:
                fig = px.bar(results.head(10), x="similarity_score", y="title", orientation="h",
                    color_discrete_sequence=["#F39C12"], height=320)
                fig.update_layout(margin=dict(t=10,b=10))
                st.plotly_chart(fig, use_container_width=True)
            st.dataframe(results, use_container_width=True)
            st.markdown("**Benchmark from these results:**")
            if "contract_amount_jmd" in results.columns:
                amts = pd.to_numeric(results["contract_amount_jmd"], errors="coerce").dropna()
                if not amts.empty:
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("Min Price", fmt_jmd(amts.min()))
                    c2.metric("Median Price", fmt_jmd(amts.median()))
                    c3.metric("Max Price", fmt_jmd(amts.max()))
                    c4.metric("Avg Price", fmt_jmd(amts.mean()))
            st.download_button("Export Similar Tenders", results.to_csv(index=False), "similar_tenders.csv", "text/csv")

# ════ TAB 18: BUDGET PREDICTOR ════
with tabs[17]:
    st.header("Budget Cycle Predictor — Feature 8")
    st.caption("Predict when a buyer will next procure in a category based on historical patterns.")
    df_pred = awards_df.copy()
    if df_pred.empty or "procuring_entity" not in df_pred.columns:
        st.warning("No data available.")
    else:
        col1, col2 = st.columns(2)
        pred_buyer = col1.selectbox("Select Buyer", sorted(df_pred["procuring_entity"].dropna().unique().tolist()), key="pred_buyer")
        pred_cat   = col2.selectbox("Select Category", ["All Categories"]+CATEGORY_LIST, key="pred_cat")
        if st.button("Predict Next Procurement Window", key="pred_go"):
            with st.spinner("Analysing procurement patterns..."):
                prediction = predict_next_procurement(pred_buyer, pred_cat if pred_cat!="All Categories" else "", df_pred)
            st.subheader("Prediction for: " + pred_buyer[:60])
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Data Points", "{:,}".format(prediction["data_points"]))
            c2.metric("Avg Monthly Contracts", str(prediction["avg_monthly_contracts"]))
            c3.metric("Confidence", prediction["confidence"].title())
            c4.metric("Next Predicted Month", prediction["next_predicted_month"] or "Insufficient data")
            if prediction["peak_months"]:
                st.success("Peak procurement months: " + ", ".join(prediction["peak_months"]))
            # Show monthly pattern
            df_buyer = df_pred[df_pred["procuring_entity"].str.lower().str.contains(pred_buyer.lower(), na=False)]
            if pred_cat != "All Categories" and "normalized_category" in df_buyer.columns:
                df_buyer = df_buyer[df_buyer["normalized_category"]==pred_cat]
            if "publication_date" in df_buyer.columns:
                df_buyer["pub_dt"] = pd.to_datetime(df_buyer["publication_date"], errors="coerce")
                df_buyer = df_buyer.dropna(subset=["pub_dt"])
                df_buyer["MonthName"] = df_buyer["pub_dt"].dt.strftime("%b")
                mo = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                mc = df_buyer.groupby("MonthName").size().reset_index(name="count")
                mc["MonthName"] = pd.Categorical(mc["MonthName"], categories=mo, ordered=True)
                mc = mc.sort_values("MonthName")
                st.subheader("Historical Monthly Pattern")
                st.plotly_chart(px.bar(mc, x="MonthName", y="count", color_discrete_sequence=["#3498DB"], height=240), use_container_width=True)

# ════ TAB 19: SOURCE REGISTRY ════
with tabs[18]:
    st.header("Multi-Source Procurement Registry — Feature 9")
    st.caption("Framework for ingesting procurement data from NHT, NWC, HEART, UDC, and other entities beyond GOJEP.")
    reg = get_source_registry()
    st.subheader("Registered Sources")
    for _, src in reg.iterrows():
        with st.expander("{} — Status: {}".format(src["name"], src["status"].upper())):
            st.write("**Base URL:** " + src["base_url"])
            st.write("**Procurement URL:** " + src["procurement_url"])
            st.write("**Notes:** " + src["notes"])
            if src["status"] == "stub":
                st.info("This source is architecturally registered. To activate: inspect the procurement page HTML, implement the scraper class in scrapers/multi_source.py, and set status to active.")
    st.markdown("---")
    st.subheader("How to Activate a New Source")
    st.code("""# In scrapers/multi_source.py, override scrape_awards():\nclass NHTScraper(BaseScraper):\n    def scrape_awards(self, max_pages=10):\n        results = []\n        for page in range(1, max_pages+1):\n            soup = self._get(self.awards_url + "?page=" + str(page))\n            if not soup: break\n            # Parse rows from soup...\n            results.append(self._normalize_row(row, self.awards_url))\n        return results""", language="python")

# ════ TAB 20: RELATIONSHIP GRAPH ════
with tabs[19]:
    st.header("Buyer-Supplier Relationship Graph — Feature 10")
    st.caption("Identify which suppliers repeatedly win contracts from the same buyers.")
    df = awards_df.copy()
    min_c = st.slider("Min contracts per relationship", 1, 10, 2, key="rg_min")
    edges = build_relationship_graph(df, min_contracts=min_c)
    if edges.empty:
        st.info("Relationship graph requires supplier_name data in awards. Populates as PDF parser and scraper run.")
        st.markdown("**What this shows once populated:**")
        st.markdown("- Buyer A awarded Supplier X 12 contracts worth JMD 450M")
        st.markdown("- Supplier Y dominates Security contracts at Ministry of Health")
        st.markdown("- Flag relationships with >6 repeat awards for transparency review")
    else:
        c1,c2,c3 = st.columns(3)
        c1.metric("Relationships Mapped", "{:,}".format(len(edges)))
        c2.metric("Unique Buyers", "{:,}".format(edges["buyer"].nunique()))
        c3.metric("Unique Suppliers", "{:,}".format(edges["supplier"].nunique()))
        st.subheader("Top Relationships by Value")
        top_e = edges.head(20)
        fig = px.scatter(top_e, x="buyer", y="supplier", size="total_value", color="contract_count",
            color_continuous_scale="Oranges", height=450,
            labels={"total_value":"Value","contract_count":"Contracts"})
        fig.update_layout(margin=dict(t=20,b=60,l=200))
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Repeat Relationship Flags")
        flags = detect_repeat_relationships(df, threshold=min_c)
        flagged = flags[flags.get("flag",pd.Series(False,index=flags.index))==True] if not flags.empty else pd.DataFrame()
        if not flagged.empty:
            st.warning("{} relationships flagged for high repeat contract count.".format(len(flagged)))
            st.dataframe(flagged, use_container_width=True)
        else:
            st.success("No unusual repeat relationship patterns detected at this threshold.")
        st.dataframe(edges, use_container_width=True)
        st.download_button("Export Relationship Data", edges.to_csv(index=False), "relationships.csv", "text/csv")
