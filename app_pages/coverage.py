# -*- coding: utf-8 -*-
"""내 커버리지 — 종목 리스트 + DART 공시 + 뉴스 + 이벤트·촉매 캘린더.

데이터 갱신 (로컬에서만 — Streamlit Cloud 는 DART 접속 차단):
    python coverage_update.py --days 45     # 공시·뉴스·주가
    python coverage_calendar.py             # 캘린더
    git add data/coverage && git commit && git push
커버리지 종목 추가/수정 = data/coverage/coverage.csv 한 줄.
"""
import datetime as dt
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "coverage"
C_BAR, C_GOLD, C_RED, C_GREEN, C_GREY = "#2a78d6", "#e8c15a", "#e05252", "#3fb27f", "#8a97aa"
STAGE_ORDER = ["In-depth", "Monitor", "Tracker", "Spread", "Revisit", "Raw Idea", "EXIT", "Closed"]
STAGE_COLOR = {"In-depth": "#f2c744", "Monitor": "#3fb27f", "Tracker": "#4fb8c9", "Spread": "#b06fc9",
               "Revisit": "#8ec9ff", "Raw Idea": "#8a97aa", "EXIT": "#eb6834", "Closed": "#5f7089"}

st.set_page_config(page_title="내 커버리지", page_icon="📋", layout="wide")

st.markdown("""<style>
.block-container { padding-top: 4rem !important; }
.lk-h { font-size: 1.18rem; font-weight: 600; background: #2a4a73; border-left: 4px solid #2e7de9;
        border-radius: 4px; padding: 6px 12px; margin: 0.9rem 0 0.5rem 0; }
.lk-h span { font-weight: 400; font-size: 0.8rem; opacity: 0.8; margin-left: 7px; }
.lk-card { background:#151d2b; border:1px solid #24304a; border-left:4px solid #2e7de9; border-radius:6px;
           padding:8px 12px; margin-bottom:8px; }
.lk-card b { font-size:0.95rem; }
.lk-tag { font-size:0.72rem; padding:1px 7px; border-radius:9px; margin-left:6px; }
</style>""", unsafe_allow_html=True)


def sub(title, note=""):
    n = f"<span>{note}</span>" if note else ""
    st.markdown(f'<div class="lk-h">{title}{n}</div>', unsafe_allow_html=True)


def _stamp(name):
    p = DATA / name
    return round(p.stat().st_mtime, 3) if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def load(name, stamp):
    p = DATA / name
    return pd.read_csv(p, dtype={"ticker": str}) if p.exists() else None


def get(name):
    return load(name, _stamp(name))


cov = get("coverage.csv")
if cov is None:
    st.error("data/coverage/coverage.csv 가 없습니다.")
    st.stop()
fil = get("filings.csv")
nws = get("news.csv")
prc = get("prices.csv")
cat = get("catalysts.csv")
meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8")) if (DATA / "meta.json").exists() else {}
today = dt.date.today()

st.title("📋 내 커버리지")
st.caption(f"종목 {len(cov)}개 · 공시·뉴스 갱신 {meta.get('as_of', '—')} · "
           "목록 원본 = 구글시트 '한국LK_MP' (여기 반영본은 data/coverage/coverage.csv) · "
           "공시 = DART, 뉴스 = 구글뉴스, 주가 = 네이버")

# ── 요약 카드
imp = fil[fil["flag"].notna() & (fil["flag"] != "")] if fil is not None else None
w1 = (today - dt.timedelta(days=7)).isoformat()
c1, c2, c3, c4 = st.columns(4)
c1.metric("커버리지 종목", f"{len(cov)}개", " · ".join(f"{k} {v}" for k, v in cov["stage"].value_counts().head(3).items()),
          delta_color="off")
if fil is not None:
    c2.metric("최근 7일 공시", f"{int((fil['rcept_dt'] >= w1).sum())}건",
              f"이 중 중요 {int(((fil['rcept_dt'] >= w1) & (fil['flag'] != '')).sum())}건", delta_color="off")
if prc is not None and len(prc):
    up = prc.nlargest(1, "chg_1w").iloc[0]
    dn = prc.nsmallest(1, "chg_1w").iloc[0]
    c3.metric("1주 최고", f"{up['name']}", f"{up['chg_1w']:+.1%}", delta_color="off")
    c4.metric("1주 최저", f"{dn['name']}", f"{dn['chg_1w']:+.1%}", delta_color="off")

tabs = st.tabs(["📌 커버리지 목록", "🗓️ 이벤트·촉매 캘린더", "📰 공시 · 뉴스 (휴가용)"])

# ================================================================ 1) 목록
with tabs[0]:
    sub("종목 목록", "Stage 별 · 주가는 네이버 종가 기준")
    d = cov.copy()
    if prc is not None:
        d = d.merge(prc[["ticker", "close", "chg_1d", "chg_1w", "chg_1m"]], on="ticker", how="left")
    if fil is not None:
        last = fil.groupby("ticker")["rcept_dt"].max().rename("최근 공시")
        nimp = fil[fil["flag"] != ""].groupby("ticker").size().rename("중요 공시")
        d = d.merge(last, on="ticker", how="left").merge(nimp, on="ticker", how="left")
    pick = st.multiselect("Stage", STAGE_ORDER, default=[s for s in STAGE_ORDER if s not in ("EXIT", "Closed")],
                          key="cv_stage")
    dd = d[d["stage"].isin(pick)] if pick else d
    dd = dd.assign(_o=dd["stage"].map({s: i for i, s in enumerate(STAGE_ORDER)})).sort_values(["_o", "name"])
    show = dd[["name", "ticker", "stage", "owner", "ss", "plan", "var_points", "idea_date",
               "close", "chg_1w", "chg_1m", "최근 공시", "중요 공시"]].rename(columns={
        "name": "종목", "ticker": "코드", "stage": "Stage", "owner": "담당", "ss": "핵심 아이디어",
        "plan": "향후 계획", "var_points": "VAR Points", "idea_date": "Idea Date",
        "close": "종가", "chg_1w": "1주", "chg_1m": "1개월"})
    st.dataframe(show, hide_index=True, use_container_width=True, height=min(60 + 35 * len(show), 900),
                 column_config={"종가": st.column_config.NumberColumn(format="%,.0f"),
                                "1주": st.column_config.NumberColumn(format="%+.1f%%"),
                                "1개월": st.column_config.NumberColumn(format="%+.1f%%"),
                                "중요 공시": st.column_config.NumberColumn(format="%d")})
    if prc is not None and len(prc):
        sub("1주 등락", "초록 = 올랐음 · 빨강 = 내렸음")
        p = prc.merge(cov[["ticker", "stage"]], on="ticker", how="left").dropna(subset=["chg_1w"])
        ch = alt.Chart(p).mark_bar().encode(
            y=alt.Y("name:N", sort="-x", title=None),
            x=alt.X("chg_1w:Q", title="1주 등락", axis=alt.Axis(format="%")),
            color=alt.condition("datum.chg_1w >= 0", alt.value(C_GREEN), alt.value(C_RED)),
            tooltip=["name", "stage", alt.Tooltip("close", title="종가", format=",.0f"),
                     alt.Tooltip("chg_1w", title="1주", format="+.1%"),
                     alt.Tooltip("chg_1m", title="1개월", format="+.1%")])
        st.altair_chart(ch.properties(height=22 * len(p) + 40), use_container_width=True)

# ================================================================ 2) 캘린더
with tabs[1]:
    if cat is None or not len(cat):
        st.info("캘린더가 아직 없습니다 — python coverage_calendar.py 를 실행하세요.")
    else:
        c = cat.copy()
        c["date"] = pd.to_datetime(c["date"]).dt.date
        c = c[c["date"] >= today].sort_values("date")
        c["D-"] = (pd.to_datetime(c["date"]) - pd.Timestamp(today)).dt.days
        sub("다가오는 이벤트·촉매", f"오늘 {today} 기준 · 확정 = 회사·공시가 날짜를 밝힌 것, 추정 = 과거 패턴·언론")
        f1, f2, f3 = st.columns([1.4, 1.4, 1])
        with f1:
            tp = st.multiselect("종류", sorted(c["type"].dropna().unique()),
                                default=sorted(c["type"].dropna().unique()), key="cv_ctype")
        with f2:
            nm = st.multiselect("종목", sorted(c["name"].unique()), default=[], key="cv_cname")
        with f3:
            hor = st.selectbox("기간", ["1주", "1개월", "3개월", "6개월", "전체"], index=2, key="cv_hor")
        lim = {"1주": 7, "1개월": 31, "3개월": 92, "6개월": 183, "전체": 9999}[hor]
        cc = c[c["type"].isin(tp) & (c["D-"] <= lim)]
        if nm:
            cc = cc[cc["name"].isin(nm)]
        if not len(cc):
            st.caption("해당 조건에 잡히는 이벤트가 없습니다.")
        else:
            ch = alt.Chart(cc).mark_circle(size=190, opacity=0.95).encode(
                x=alt.X("date:T", title=None), y=alt.Y("name:N", title=None, sort=alt.SortField("date")),
                color=alt.Color("impact:N", title="영향",
                                scale=alt.Scale(domain=["positive", "neutral", "negative"],
                                                range=[C_GREEN, C_GREY, C_RED]), legend=alt.Legend(orient="top")),
                shape=alt.Shape("confirmed:N", title="확정", scale=alt.Scale(domain=["Y", "N"], range=["circle", "diamond"]),
                                legend=alt.Legend(orient="top")),
                tooltip=["date", "name", "type", "title", "detail", "date_kind", "source"])
            now = alt.Chart(pd.DataFrame({"d": [today]})).mark_rule(color=C_GOLD, strokeDash=[4, 3]).encode(x="d:T")
            st.altair_chart((ch + now).properties(height=40 + 30 * cc["name"].nunique()), use_container_width=True)

            for _, x in cc.iterrows():
                col = {"positive": C_GREEN, "negative": C_RED}.get(str(x["impact"]), C_GREY)
                dd_ = "오늘" if x["D-"] == 0 else f"D-{x['D-']}"
                ok = "확정" if str(x["confirmed"]).upper() == "Y" else str(x.get("date_kind", "추정"))
                link = f" · <a href='{x['url']}' target='_blank'>출처</a>" if isinstance(x.get("url"), str) and x["url"].startswith("http") else ""
                st.markdown(
                    f"<div class='lk-card' style='border-left-color:{col}'>"
                    f"<b>{x['date']} · {dd_} · {x['name']}</b>"
                    f"<span class='lk-tag' style='background:{col}22;color:{col}'>{x['type']}</span>"
                    f"<span class='lk-tag' style='background:#24304a;color:#9ab'>{ok}</span><br>"
                    f"{x['title']}"
                    + (f"<br><span style='color:#8a97aa;font-size:0.85rem'>{x['detail']}</span>"
                       if isinstance(x.get("detail"), str) and x["detail"] else "")
                    + f"<span style='color:#66738a;font-size:0.78rem'> · {x.get('source', '')}{link}</span></div>",
                    unsafe_allow_html=True)
        st.caption("실적 보고서 날짜는 DART 과거 제출일의 중앙값으로 추정한 것입니다(마름모 = 추정). "
                   "회사가 날짜를 밝히면 data/coverage/catalysts_manual.csv 에 확정일로 적으세요.")

# ================================================================ 3) 공시·뉴스
with tabs[2]:
    sub("휴가 중 체크리스트", "중요 공시부터 · 아래로 갈수록 덜 급함")
    c1_, c2_ = st.columns([1, 1])
    with c1_:
        back = st.selectbox("최근", ["3일", "7일", "14일", "30일", "전체"], index=1, key="cv_back")
    with c2_:
        only = st.toggle("중요 공시만", value=True, key="cv_only")
    nb = {"3일": 3, "7일": 7, "14일": 14, "30일": 30, "전체": 3650}[back]
    since = (today - dt.timedelta(days=nb)).isoformat()

    if fil is not None and len(fil):
        f = fil[fil["rcept_dt"] >= since].copy()
        if only:
            f = f[f["flag"] != ""]
        st.markdown(f"**DART 공시 {len(f)}건**")
        if len(f):
            f = f.merge(cov[["ticker", "stage"]], on="ticker", how="left")
            st.dataframe(f[["rcept_dt", "name", "stage", "flag", "report_nm", "url"]].rename(columns={
                "rcept_dt": "날짜", "name": "종목", "stage": "Stage", "flag": "분류", "report_nm": "공시 제목", "url": "링크"}),
                hide_index=True, use_container_width=True, height=min(60 + 35 * len(f), 620),
                column_config={"링크": st.column_config.LinkColumn(display_text="DART")})
        else:
            st.caption("해당 기간에 없습니다.")

    if nws is not None and len(nws):
        st.markdown("")
        sub("뉴스", "구글뉴스 · 종목명 검색 · 최신순")
        n = nws.copy()
        pick_n = st.multiselect("종목", sorted(n["name"].unique()), default=[], key="cv_news_nm")
        if pick_n:
            n = n[n["name"].isin(pick_n)]
        n = n.sort_values("date", ascending=False).head(300)
        st.dataframe(n[["date", "name", "title", "press", "url"]].rename(columns={
            "date": "시각", "name": "종목", "title": "제목", "press": "매체", "url": "링크"}),
            hide_index=True, use_container_width=True, height=560,
            column_config={"링크": st.column_config.LinkColumn(display_text="열기")})
    st.caption("갱신은 로컬에서 `python coverage_update.py --days 45` → `python coverage_calendar.py` → git push. "
               "Streamlit Cloud 는 해외 IP 라 DART 직접 조회가 막혀 있어 미리 받아 둔 CSV 를 보여 줍니다.")
