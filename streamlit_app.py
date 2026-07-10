"""BuzzTrend — Sometrend 스타일 소셜 버즈 분석 대시보드 (Streamlit).

Run:
    python -m streamlit run streamlit_app.py
"""
from __future__ import annotations

import io
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import altair as alt
import pandas as pd
import streamlit as st

from app import config
from app.database import init_db, session_scope
from app.models import Keyword
from app.services import analytics
from app.services.alerts import check_alerts
from app.services.collection import collect_for_day
from app.services.mentions import mentions_range, parse_include
from app.services.seed import add_keyword, maybe_seed, remove_keyword

st.set_page_config(page_title="BuzzTrend", page_icon="📈", layout="wide")

LABELS = {c["key"]: c["label"] for c in config.CHANNELS}
COLORS = {c["key"]: c["color"] for c in config.CHANNELS}
LABEL_TO_KEY = {c["label"]: c["key"] for c in config.CHANNELS}


@st.cache_resource
def bootstrap():
    init_db()
    with session_scope() as s:
        maybe_seed(s)
    return True


bootstrap()


@st.cache_data(ttl=900, show_spinner=False)
def cached_mentions(term: str, channels: tuple, start_iso: str, end_iso: str,
                    include_raw: str, per_day: int):
    words = parse_include(include_raw)
    return mentions_range(term, list(channels),
                          date.fromisoformat(start_iso),
                          date.fromisoformat(end_iso),
                          words, per_day)


# =========================== 사이드바 ===========================
with st.sidebar:
    st.markdown("## 📈 Buzz**Trend**")
    st.caption("🟠 데모 / 모의 데이터" if config.USE_MOCK else "🟢 실시간 데이터")

    # ---- 검색 키워드 관리 (추가 / 삭제) ----
    st.markdown("#### 🔍 검색 키워드")
    with session_scope() as s:
        keywords = [(k.id, k.term)
                    for k in s.query(Keyword).order_by(Keyword.id).all()]

    for kid, term in keywords:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"&nbsp;• **{term}**")
        if c2.button("✕", key=f"del_{kid}", help=f"'{term}' 삭제"):
            with session_scope() as s:
                remove_keyword(s, kid)
            st.cache_data.clear()
            st.rerun()

    new_term = st.text_input("키워드 추가", placeholder="예: 하츄핑",
                             label_visibility="collapsed")
    if st.button("➕ 키워드 추가", width="stretch"):
        if new_term.strip():
            with st.spinner("12개월 데이터 생성 중…"):
                with session_scope() as s:
                    add_keyword(s, new_term)
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("키워드를 입력해 주세요.")

    st.divider()

    # ---- 포함어 ----
    st.markdown("#### 📝 포함어")
    include_raw = st.text_input(
        "포함어", placeholder="예: 콘서트, 굿즈", label_visibility="collapsed",
        help="이 단어가 포함된 문서만 집계합니다. 부분 일치 — "
             "'하츄핑' 입력 시 '하츄핑콘서트'도 매칭됩니다. "
             "여러 개 입력 시 모두 포함(AND).")
    if include_raw.strip():
        st.caption(f"필터 적용중: **{include_raw.strip()}** (표본 기반 추정)")

    st.divider()

    # ---- 기간 ----
    st.markdown("#### 📅 기간")
    today = date.today()
    max_start = today - timedelta(days=config.SEED_DAYS)
    preset = st.radio("기간 선택", ["1개월", "3개월", "6개월", "12개월", "직접 설정"],
                      index=3, horizontal=True, label_visibility="collapsed")
    preset_days = {"1개월": 30, "3개월": 90, "6개월": 180, "12개월": 365}
    if preset == "직접 설정":
        picked = st.date_input("날짜 범위", value=(max_start, today),
                               min_value=max_start, max_value=today)
        if isinstance(picked, tuple) and len(picked) == 2:
            start_d, end_d = picked
        else:
            start_d, end_d = max_start, today
    else:
        end_d = today
        start_d = max(max_start, today - timedelta(days=preset_days[preset]))
    st.caption(f"{start_d} ~ {end_d} ({(end_d - start_d).days + 1}일)")

    st.divider()

    # ---- 출처 ----
    st.markdown("#### 📡 출처 (중복 선택 가능)")
    default_labels = [LABELS[k] for k in config.DEFAULT_SELECTED_CHANNELS]
    sel_labels = st.multiselect("출처", [c["label"] for c in config.CHANNELS],
                                default=default_labels,
                                label_visibility="collapsed")
    sel_channels = [LABEL_TO_KEY[l] for l in sel_labels]

    st.divider()
    if st.button("↻ 오늘 데이터 수집", width="stretch"):
        with st.spinner("수집 중…"):
            with session_scope() as s:
                collect_for_day(s, today)
                check_alerts(s, today)
        st.cache_data.clear()
        st.rerun()


# =========================== 본문 ===========================
if not keywords:
    st.info("사이드바에서 키워드를 추가해 주세요.")
    st.stop()
if not sel_channels:
    st.warning("출처를 1개 이상 선택해 주세요.")
    st.stop()

term_options = {term: kid for kid, term in keywords}
sel_col1, sel_col2 = st.columns([3, 2])
with sel_col1:
    sel_term = st.selectbox("분석 키워드", list(term_options), label_visibility="collapsed")
sel_kid = term_options[sel_term]
with sel_col2:
    st.markdown(f"### 분석 결과 · :violet[{sel_term}]")

include_words = parse_include(include_raw)

tab_main, tab_compare, tab_alerts = st.tabs(["언급량 분석", "키워드 비교", "급증 알림"])

# --------------------------- 언급량 분석 ---------------------------
with tab_main:
    # daily counts: DB when unfiltered, sample-scaled estimate under 포함어
    if include_words:
        mention_rows, daily_rows = cached_mentions(
            sel_term, tuple(sel_channels), start_d.isoformat(),
            end_d.isoformat(), include_raw.strip(), 6)
        daily_df = pd.DataFrame(daily_rows)
    else:
        mention_rows, _ = cached_mentions(
            sel_term, tuple(sel_channels), start_d.isoformat(),
            end_d.isoformat(), "", 6)
        with session_scope() as s:
            ts = analytics.timeseries_range(s, sel_kid, start_d, end_d,
                                            sel_channels)
        recs = []
        for ch in sel_channels:
            for d_iso, c in zip(ts["dates"], ts["series"][ch]):
                recs.append({"date": date.fromisoformat(d_iso),
                             "channel": ch, "count": c})
        daily_df = pd.DataFrame(recs)

    daily_df["date"] = pd.to_datetime(daily_df["date"])
    daily_df["채널"] = daily_df["channel"].map(LABELS)

    # ---- 요약 지표 ----
    total_all = int(daily_df["count"].sum())
    per_ch = daily_df.groupby("channel")["count"].sum()
    cols = st.columns(len(sel_channels) + 1)
    cols[0].metric("전체", f"{total_all:,}건")
    for col, ch in zip(cols[1:], sel_channels):
        col.metric(LABELS[ch], f"{int(per_ch.get(ch, 0)):,}건")

    # ---- 언급량 추이 ----
    st.markdown("#### 언급량 추이")
    gran = st.radio("granularity", ["일별", "주별", "월별"], index=1 if
                    (end_d - start_d).days > 120 else 0, horizontal=True,
                    label_visibility="collapsed")
    rule = {"일별": "D", "주별": "W-MON", "월별": "MS"}[gran]

    pivot = (daily_df.pivot_table(index="date", columns="채널",
                                  values="count", aggfunc="sum")
             .resample(rule).sum())
    long_df = pivot.reset_index().melt("date", var_name="채널",
                                       value_name="언급량")
    total_df = pivot.sum(axis=1).reset_index()
    total_df.columns = ["date", "전체"]

    domain = [LABELS[ch] for ch in sel_channels]
    color_range = [COLORS[ch] for ch in sel_channels]

    area = alt.Chart(total_df).mark_area(
        color="#d1d5db", opacity=0.45, interpolate="monotone"
    ).encode(x=alt.X("date:T", title=None), y=alt.Y("전체:Q", title=None),
             tooltip=[alt.Tooltip("date:T", title="날짜"),
                      alt.Tooltip("전체:Q", format=",")])
    lines = alt.Chart(long_df).mark_line(strokeWidth=2.2,
                                         interpolate="monotone").encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("언급량:Q", title=None),
        color=alt.Color("채널:N", scale=alt.Scale(domain=domain,
                                                  range=color_range),
                        legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("date:T", title="날짜"), "채널:N",
                 alt.Tooltip("언급량:Q", format=",")])
    st.altair_chart((area + lines).properties(height=330), width="stretch")
    if include_words:
        st.caption("⚠️ 포함어 필터 적용 — 표본 매칭 비율 기반 추정치입니다.")

    # ---- 출처별 구성 + 원문 ----
    left, right = st.columns([2, 3])

    with left:
        st.markdown("#### 출처별 언급량 구성")
        share_df = (daily_df.groupby("채널")["count"].sum()
                    .reset_index().rename(columns={"count": "언급량"}))
        share_df = share_df[share_df["언급량"] > 0]
        if share_df.empty:
            st.info("데이터가 없습니다.")
        else:
            pie = alt.Chart(share_df).mark_arc(innerRadius=55).encode(
                theta="언급량:Q",
                color=alt.Color("채널:N",
                                scale=alt.Scale(domain=domain,
                                                range=color_range),
                                legend=alt.Legend(orient="bottom")),
                tooltip=["채널:N", alt.Tooltip("언급량:Q", format=",")])
            st.altair_chart(pie.properties(height=290), width="stretch")
            st.dataframe(share_df.sort_values("언급량", ascending=False)
                         .style.format({"언급량": "{:,}"}),
                         hide_index=True, width="stretch")

    with right:
        st.markdown("#### 원문 (표본)")
        st.caption("모의 데이터 표본입니다. 링크를 클릭하면 해당 플랫폼의 "
                   "실제 검색 결과가 열립니다.")
        mdf = pd.DataFrame(mention_rows)
        if mdf.empty:
            st.info("조건에 맞는 원문이 없습니다.")
        else:
            show = mdf[["date", "channel_label", "author", "text",
                        "likes", "comments", "url"]].rename(columns={
                "date": "날짜", "channel_label": "채널", "author": "작성자",
                "text": "내용", "likes": "좋아요", "comments": "댓글",
                "url": "원문 보기"})
            st.dataframe(
                show.head(400), hide_index=True, width="stretch", height=380,
                column_config={
                    "원문 보기": st.column_config.LinkColumn(
                        "원문 보기", display_text="🔗 원문"),
                    "좋아요": st.column_config.NumberColumn(format="localized"),
                    "댓글": st.column_config.NumberColumn(format="localized"),
                })

    # ---- 엑셀 다운로드 ----
    st.markdown("#### 데이터 다운로드")

    @st.cache_data(ttl=900, show_spinner=False)
    def build_excel(term, channels, s_iso, e_iso, inc, _daily_json, _mention_json):
        d_df = pd.read_json(io.StringIO(_daily_json))
        m_df = pd.read_json(io.StringIO(_mention_json))
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            d_df.to_excel(w, sheet_name="일별 언급량", index=False)
            if not m_df.empty:
                m_df.to_excel(w, sheet_name="원문 표본", index=False)
        return buf.getvalue()

    export_daily = (daily_df[["date", "채널", "count"]]
                    .rename(columns={"date": "날짜", "count": "언급량"}))
    export_daily["날짜"] = export_daily["날짜"].dt.strftime("%Y-%m-%d")
    export_mentions = pd.DataFrame(mention_rows)
    xlsx = build_excel(sel_term, tuple(sel_channels), start_d.isoformat(),
                       end_d.isoformat(), include_raw.strip(),
                       export_daily.to_json(), export_mentions.to_json())
    st.download_button(
        "📥 엑셀(Raw Data) 다운로드", xlsx,
        file_name=f"buzztrend_{sel_term}_{start_d}_{end_d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --------------------------- 키워드 비교 ---------------------------
with tab_compare:
    st.markdown("#### 전체 키워드 언급량 비교")
    comp = {}
    idx = None
    with session_scope() as s:
        for term, kid in term_options.items():
            ts = analytics.timeseries_range(s, kid, start_d, end_d,
                                            sel_channels)
            comp[term] = ts["totals"]
            idx = ts["dates"]
    comp_df = pd.DataFrame(comp, index=pd.to_datetime(idx))
    rule2 = "W-MON" if (end_d - start_d).days > 120 else "D"
    comp_long = (comp_df.resample(rule2).sum().reset_index()
                 .melt("index", var_name="키워드", value_name="언급량"))
    chart = alt.Chart(comp_long).mark_line(strokeWidth=2.2,
                                           interpolate="monotone").encode(
        x=alt.X("index:T", title=None),
        y=alt.Y("언급량:Q", title=None),
        color=alt.Color("키워드:N", legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("index:T", title="날짜"), "키워드:N",
                 alt.Tooltip("언급량:Q", format=",")])
    st.altair_chart(chart.properties(height=340), width="stretch")

    totals_tbl = (comp_df.sum().sort_values(ascending=False)
                  .reset_index())
    totals_tbl.columns = ["키워드", "기간 내 총 언급량"]
    st.dataframe(totals_tbl.style.format({"기간 내 총 언급량": "{:,}"}),
                 hide_index=True, width="stretch")

# --------------------------- 급증 알림 ---------------------------
with tab_alerts:
    st.caption("일별 언급량이 직전 7일 평균 대비 "
               f"{config.ALERT_SPIKE_RATIO}배 이상이면 알림이 생성됩니다.")
    with session_scope() as s:
        alerts = analytics.recent_alerts(s, limit=300)
    alerts = [a for a in alerts if a["channel"] in sel_channels]
    if not alerts:
        st.info("알림이 없습니다.")
    else:
        adf = pd.DataFrame([{
            "날짜": a["date"], "키워드": a["term"],
            "채널": a["channel_label"], "언급량": a["count"],
            "7일 평균": round(a["baseline"]), "배수": f'{a["ratio"]}×',
        } for a in alerts])
        st.dataframe(adf, hide_index=True, width="stretch", height=430)
