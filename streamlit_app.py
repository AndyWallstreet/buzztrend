"""BuzzTrend — Streamlit dashboard.

Reuses the existing backend (app/collectors, app/services, SQLite DB). Edit this
file in plain Python to change the UI — no HTML/JS needed.

Run:
    python -m streamlit run streamlit_app.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from app import config
from app.database import init_db, session_scope
from app.models import Keyword
from app.services import analytics
from app.services.alerts import check_alerts
from app.services.collection import collect_for_day
from app.services.seed import add_keyword, maybe_seed

st.set_page_config(page_title="BuzzTrend", page_icon="📈", layout="wide")

LABELS = {c["key"]: c["label"] for c in config.CHANNELS}
REGION = {c["key"]: c["region"] for c in config.CHANNELS}


@st.cache_resource
def bootstrap():
    """Runs once per server start: create tables + seed demo data if empty."""
    init_db()
    with session_scope() as s:
        maybe_seed(s)
    return True


bootstrap()


# --------------------------- sidebar / controls ---------------------------
with st.sidebar:
    st.markdown("## Buzz**Trend**")
    if config.USE_MOCK:
        st.caption("🟠 DEMO / MOCK DATA")
    else:
        st.caption("🟢 LIVE DATA")

    days = st.select_slider("Time range (days)",
                            options=[7, 14, 30, 60, 90], value=30)

    st.divider()
    st.markdown("**Track a new keyword**")
    new_term = st.text_input("Keyword", label_visibility="collapsed",
                             placeholder="e.g. 삼성전자, Tesla")
    if st.button("➕ Track", width="stretch"):
        if new_term.strip():
            with st.spinner("Backfilling history…"):
                with session_scope() as s:
                    add_keyword(s, new_term)
            st.success(f"Now tracking “{new_term.strip()}”.")
            st.rerun()
        else:
            st.warning("Enter a keyword first.")

    st.divider()
    if st.button("↻ Collect today's buzz", width="stretch"):
        with st.spinner("Collecting…"):
            with session_scope() as s:
                points = collect_for_day(s, date.today())
                new_alerts = check_alerts(s, date.today())
        st.success(f"Collected {points} points · {new_alerts} new alert(s).")
        st.rerun()


# --------------------------- load data ---------------------------
with session_scope() as s:
    overview = analytics.keyword_overview(s, days)
    alerts = analytics.recent_alerts(s, limit=200)

st.title("📈 Buzz Dashboard")

if not overview:
    st.info("No keywords yet — add one from the sidebar to get started.")
    st.stop()

tab_overview, tab_detail, tab_alerts = st.tabs(
    ["Overview", "Keyword detail", f"Alerts ({len(alerts)})"]
)


# --------------------------- Overview ---------------------------
with tab_overview:
    metric_cols = st.columns(min(4, len(overview)))
    for col, k in zip(metric_cols, overview[:4]):
        col.metric(k["term"], f'{k["today"]:,}',
                   f'{k["change_pct"]:+.1f}% vs yesterday')

    st.subheader("Total buzz over time")
    trend = {}
    idx = None
    with session_scope() as s:
        for k in overview:
            ts = analytics.timeseries(s, k["id"], days)
            trend[k["term"]] = ts["totals"]
            idx = ts["dates"]
    trend_df = pd.DataFrame(trend, index=pd.to_datetime(idx))
    st.line_chart(trend_df)

    st.subheader("Keywords")
    table = pd.DataFrame([{
        "Keyword": k["term"],
        "Today": k["today"],
        f"Total ({days}d)": k["total"],
        "Δ% vs yesterday": k["change_pct"],
    } for k in overview])
    st.dataframe(table, width="stretch", hide_index=True)


# --------------------------- Keyword detail ---------------------------
with tab_detail:
    term_to_id = {k["term"]: k["id"] for k in overview}
    selected = st.selectbox("Keyword", list(term_to_id))
    kid = term_to_id[selected]

    with session_scope() as s:
        ts = analytics.timeseries(s, kid, days)
        bd = analytics.breakdown(s, kid, days)

    total = sum(b["total"] for b in bd) or 1
    kv = next(k for k in overview if k["id"] == kid)
    m1, m2, m3 = st.columns(3)
    m1.metric("Today", f'{kv["today"]:,}')
    m2.metric(f"Total ({days}d)", f'{kv["total"]:,}')
    m3.metric("Change", f'{kv["change_pct"]:+.1f}%')

    st.subheader("Buzz over time by channel")
    series_df = pd.DataFrame(
        {LABELS[ch]: ts["series"][ch] for ch in config.CHANNEL_KEYS},
        index=pd.to_datetime(ts["dates"]),
    )
    st.line_chart(series_df)

    left, right = st.columns([1, 1])
    bd_df = pd.DataFrame([{
        "Channel": LABELS[b["channel"]],
        "Region": REGION[b["channel"]].upper(),
        "Total": b["total"],
        "Share %": round(b["total"] / total * 100, 1),
    } for b in bd]).sort_values("Total", ascending=False)

    with left:
        st.subheader("By channel")
        st.bar_chart(bd_df.set_index("Channel")["Total"])
    with right:
        st.subheader("Breakdown")
        st.dataframe(bd_df, width="stretch", hide_index=True)

    with st.expander("Manage keyword"):
        if st.button(f"🗑 Stop tracking “{selected}”"):
            with session_scope() as s:
                obj = s.get(Keyword, kid)
                if obj:
                    s.delete(obj)
                    s.commit()
            st.rerun()


# --------------------------- Alerts ---------------------------
with tab_alerts:
    st.caption("Fires when a channel's daily buzz jumps well above its "
               "trailing 7-day average.")
    if not alerts:
        st.info("No alerts yet.")
    else:
        alerts_df = pd.DataFrame([{
            "Date": a["date"],
            "Keyword": a["term"],
            "Channel": a["channel_label"],
            "Count": a["count"],
            "Baseline": round(a["baseline"]),
            "Spike": f'{a["ratio"]}×',
        } for a in alerts])
        st.dataframe(alerts_df, width="stretch", hide_index=True)
